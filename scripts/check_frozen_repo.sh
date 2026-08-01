#!/usr/bin/env bash
# R6 冻结校验（design.md §8.2 R6-S1）。
#
# voice-translate-v2 除 openspec/changes/pipecat-native-p1/** 外必须零改动。
# 基线 = 门二 design.md 批准时的 HEAD，写死在此处。覆盖三路合并：
#   1) git log --all --not baseline --name-only —— 已提交的改动，覆盖**全部
#      本地分支**（不止当前分支：red-team 20260801 实测只查当前分支会漏判
#      "改动提交在另一分支再切回来"这条路径，MNT-001）
#   2) git status --porcelain —— 未提交的改动
#   3) git stash list —— 被 stash 收起的改动（同一红队实测点）
#
# 已知残留限制（MNT-001 未闭合部分，故意不做）：被 .gitignore 覆盖的文件若其
# **内容**被修改，git 从未跟踪其历史，因此本脚本结构性看不见（git status
# --ignored 只能列出"当前存在哪些被忽略的路径"，不能判断内容有没有变化，
# 而 voice-translate-v2 有 56 个既有被忽略文件，逐一做内容基线快照超出本次
# "单文件小修复"的范围——不做假装能查的心理安慰式检查）。
set -euo pipefail

REPO="${VOICE_TRANSLATE_V2_REPO:-$HOME/git/voice-translate-v2}"
BASELINE_SHA="e5a3b4a"
ALLOWED_PREFIX="openspec/changes/pipecat-native-p1/"
# 会话前既有未跟踪项，非本变更产生（design.md §8.2 R6-S1 修正②）。
WHITELIST=(".codegraph/" ".repomixignore" "va.svg")

cd "$REPO"

# MNT-002(门三 20260801)：目录型白名单项（尾带 /）用前缀匹配，文件型白名单项
# 用精确匹配——原实现全用前缀匹配，会把 ".repomixignore.bak" 之类误判为已放行。
is_allowed() {
    local path="$1"
    [[ "$path" == "$ALLOWED_PREFIX"* ]] && return 0
    for w in "${WHITELIST[@]}"; do
        if [[ "$w" == */ ]]; then
            [[ "$path" == "$w"* ]] && return 0
        else
            [[ "$path" == "$w" ]] && return 0
        fi
    done
    return 1
}

paths=()
while IFS= read -r path; do
    [[ -n "$path" ]] && paths+=("$path")
done < <(git log --all --not "$BASELINE_SHA" --name-only --pretty=format: 2>/dev/null)

while IFS= read -r path; do
    [[ -n "$path" ]] && paths+=("$path")
done < <(git status --porcelain | sed -E 's/^...//')

while IFS= read -r stash_sha; do
    [[ -z "$stash_sha" ]] && continue
    while IFS= read -r path; do
        [[ -n "$path" ]] && paths+=("$path")
    done < <(git diff --name-only "${BASELINE_SHA}" "$stash_sha" 2>/dev/null)
done < <(git stash list --format=%H)

offenders=()
for path in "${paths[@]}"; do
    is_allowed "$path" || offenders+=("$path")
done

if [[ ${#offenders[@]} -gt 0 ]]; then
    mapfile -t offenders < <(printf '%s\n' "${offenders[@]}" | sort -u)
    echo "R6 冻结校验失败：以下路径在基线 ${BASELINE_SHA} 之外被改动/新增（含全部分支与 stash）："
    printf '  %s\n' "${offenders[@]}"
    exit 1
fi

echo "R6 冻结校验通过：voice-translate-v2 除 ${ALLOWED_PREFIX}** 与既有白名单外零改动（已覆盖全部分支/stash，未覆盖 .gitignore 内容篡改，见脚本头注）。"
exit 0
