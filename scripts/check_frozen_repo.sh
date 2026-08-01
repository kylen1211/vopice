#!/usr/bin/env bash
# R6 冻结校验（design.md §8.2 R6-S1）。
#
# voice-translate-v2 除 openspec/changes/pipecat-native-p1/** 外必须零改动。
# 基线 = 本变更起点 commit（门二 design.md 批准时的 HEAD），写死在此处：
# checked against `git diff --name-only <基线>..HEAD` ∪ `git status
# --porcelain` 的并集 —— 前者抓已提交的改动，后者抓未提交的，缺一个都会漏判。
set -euo pipefail

REPO="${VOICE_TRANSLATE_V2_REPO:-$HOME/git/voice-translate-v2}"
BASELINE_SHA="e5a3b4a"
ALLOWED_PREFIX="openspec/changes/pipecat-native-p1/"
# 会话前既有未跟踪项，非本变更产生（design.md §8.2 R6-S1 修正②）。
WHITELIST=(".codegraph/" ".repomixignore" "va.svg")

cd "$REPO"

is_allowed() {
    local path="$1"
    [[ "$path" == "$ALLOWED_PREFIX"* ]] && return 0
    for w in "${WHITELIST[@]}"; do
        [[ "$path" == "$w"* ]] && return 0
    done
    return 1
}

offenders=()
while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    is_allowed "$path" || offenders+=("$path")
done < <(
    {
        git diff --name-only "${BASELINE_SHA}..HEAD"
        git status --porcelain | sed -E 's/^...//'
    } | sort -u
)

if [[ ${#offenders[@]} -gt 0 ]]; then
    echo "R6 冻结校验失败：以下路径在基线 ${BASELINE_SHA} 之外被改动/新增："
    printf '  %s\n' "${offenders[@]}"
    exit 1
fi

echo "R6 冻结校验通过：voice-translate-v2 除 ${ALLOWED_PREFIX}** 与既有白名单外零改动。"
exit 0
