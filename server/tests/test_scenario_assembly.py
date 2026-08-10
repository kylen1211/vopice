"""Assembly-contract tests for `server/bot.py` (scenario-assembly T-3,
contract/cases.md §0.4).

本文件出**装配契约层**：一律经 `load_config()` → `bot.assemble_pipeline()`
走完整装配链路，断言落在真实构造出的对象上（FR-2/FR-3/FR-8/FR-12）——
不手工构造 `Config`/`ScenarioTemplate` dataclass 绕过 `load_config()` 当证据
(P55)。纯常量/纯函数断言归 `test_scenarios.py`(T-1)；行为级 eval 归 T-4。

用例名与契约锚点关键字的对应（`-k` 复核用）：
- `template_drives`  → SA-04
- `dual_brain_off`   → SA-05
- `dual_brain_on`    → SA-06
- `session_config`   → SA-11
- `error_attribution`→ SA-14
- `dispatch_unaffected` → SA-15
"""

import asyncio
import contextlib

import loguru
from pipecat.frames.frames import ErrorFrame
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.processors.frame_processor import FrameProcessor

import prompts
import task_dispatch


class _FakeTransport:
    """最小 transport 桩：只暴露 `assemble_pipeline()` 实际用到的
    `input()`/`output()`，与 `test_dual_brain.py::TestAssemblePipeline` 同款
    手法（本文件不 import 测试模块，独立复刻一份最小实现，保持每个测试文件
    自包含——同 `test_bot.py` 模块头对"为何新建文件而不复用既有测试文件"的
    职责边界说明）。"""

    def __init__(self):
        self._input = FrameProcessor(name="fake-transport-input")
        self._output = FrameProcessor(name="fake-transport-output")

    def input(self):
        return self._input

    def output(self):
        return self._output


class _FakeWorker:
    """最小 worker 桩：只暴露 `make_pipeline_error_handler` 返回的 handler
    实际调用到的 `queue_frames()`，把送进来的帧原样收集供断言。"""

    def __init__(self):
        self.queued = []

    async def queue_frames(self, frames):
        self.queued.extend(frames)


@contextlib.contextmanager
def _capture_logs():
    """临时挂一个 loguru sink，只捕获本次 `with` 块内产生的日志文本
    （同 `test_dual_brain.py::_capture_dual_brain_logs` 手法，`caplog` 捕获
    不到 loguru 的独立 sink 系统）。"""
    captured: list[str] = []
    sink_id = loguru.logger.add(lambda msg: captured.append(msg.record["message"]), level="INFO")
    try:
        yield captured
    finally:
        loguru.logger.remove(sink_id)


def test_template_drives_prompt_and_service_construction(bot_module, monkeypatch):
    """SA-04(FR-2/FR-8)：两模板经 `load_config()` → `assemble_pipeline()`
    走完整装配，读真实构造对象。

    prompt 面：身份段锚点分别分段锁定（语言段差异是 SA-22 的职责，不在此重复，
    不用"整串不相等"蒙混过关）。
    服务面：`voice_chat` 装出的 `stt` 是 Soniox 实例、`english_tutor` 装出的
    `stt` 是 `AssemblyAISTTService` 实例（契约 §0.2 判定口径②，修订 R2）。
    """
    from pipecat.services.assemblyai.stt import AssemblyAISTTService
    from pipecat.services.soniox.stt import SonioxSTTService

    cfg_voice = bot_module.load_config()  # SCENARIO 未设置 → 默认 voice_chat
    assert cfg_voice.template.id == "voice_chat"
    assembled_voice = bot_module.assemble_pipeline(cfg_voice, _FakeTransport())

    monkeypatch.setenv("SCENARIO", "english_tutor")
    cfg_tutor = bot_module.load_config()
    assert cfg_tutor.template.id == "english_tutor"
    assembled_tutor = bot_module.assemble_pipeline(cfg_tutor, _FakeTransport())

    voice_instruction = assembled_voice.fast_llm._settings.system_instruction
    tutor_instruction = assembled_tutor.fast_llm._settings.system_instruction
    assert prompts.IDENTITY_DEFAULT_SECTION in voice_instruction, (
        "voice_chat 装配出的 system_instruction 必须含默认身份段"
    )
    assert prompts.IDENTITY_DEFAULT_SECTION not in tutor_instruction, (
        "english_tutor 装配出的 system_instruction 不得含默认身份段"
    )
    assert prompts.IDENTITY_ENGLISH_TUTOR_SECTION in tutor_instruction, (
        "english_tutor 装配出的 system_instruction 必须含陪练身份段"
    )
    assert prompts.IDENTITY_ENGLISH_TUTOR_SECTION not in voice_instruction, (
        "voice_chat 装配出的 system_instruction 不得含陪练身份段"
    )

    assert isinstance(assembled_voice.stt, SonioxSTTService), (
        "voice_chat 未声明 stt_provider 覆盖，应沿用默认 soniox"
    )
    assert isinstance(assembled_tutor.stt, AssemblyAISTTService), (
        "english_tutor 声明 stt_provider=assemblyai，装出的 stt 必须是 AssemblyAISTTService"
    )

    # s6 review Important-2 可选加固：生效的 fast_llm_model 真的传进了构造
    # 对象（不只是 Config 上的一个字段），钉死 ADR-5 合并结果的落地那一步。
    assert assembled_voice.fast_llm._settings.model == cfg_voice.fast_llm_model
    assert assembled_tutor.fast_llm._settings.model == cfg_tutor.fast_llm_model


def test_dual_brain_off_degrades_pipeline_to_single_chain(bot_module):
    """SA-05(FR-12)：关闭态（`bot_module` 默认 `DUAL_BRAIN_ENABLED` 未设置）
    逐项核对 contract §0.4 关闭态表。"""
    assembled = bot_module.assemble_pipeline(bot_module.cfg, _FakeTransport())

    assert assembled.slow_llm is None
    assert assembled.slow_context is None
    assert assembled.sentence_aggregator is None
    assert assembled.producer is None
    assert assembled.consumer is None

    assert not any(isinstance(p, ParallelPipeline) for p in assembled.pipeline.processors), (
        "关闭态管线必须是单链，不得含 ParallelPipeline"
    )

    assert prompts.DUAL_BRAIN_SECTION not in assembled.fast_llm._settings.system_instruction, (
        "关闭态 system_instruction 不得含 DUAL_BRAIN_SECTION"
    )

    assert list(assembled.rtvi_observer_params.ignored_sources) == []
    assert assembled.rtvi_observer_params.user_llm_enabled is False


def test_dual_brain_on_matches_2026_08_10_baseline(bot_module_dual_brain):
    """SA-06(FR-12/FR-9)：开启态（T-2 的 `bot_module_dual_brain` fixture）与
    2026-08-10 基线逐件等价——双脑分支挂载、`DUAL_BRAIN_SECTION` 注入、
    `ignored_sources` 仍以对象身份列 `slow_llm`/`sentence_aggregator`/
    `producer`。"""
    assembled = bot_module_dual_brain.assemble_pipeline(
        bot_module_dual_brain.cfg, _FakeTransport()
    )

    assert assembled.slow_llm is not None
    assert assembled.slow_context is not None
    assert assembled.sentence_aggregator is not None
    assert assembled.producer is not None
    assert assembled.consumer is not None

    assert any(isinstance(p, ParallelPipeline) for p in assembled.pipeline.processors), (
        "开启态管线必须含 ParallelPipeline"
    )

    assert prompts.DUAL_BRAIN_SECTION in assembled.fast_llm._settings.system_instruction, (
        "开启态 system_instruction 必须含 DUAL_BRAIN_SECTION"
    )

    ignored = list(assembled.rtvi_observer_params.ignored_sources)
    assert set(ignored) == {
        assembled.slow_llm,
        assembled.sentence_aggregator,
        assembled.producer,
    }
    assert len(ignored) == 3, "ignored_sources 不得含重复/多余项"
    assert assembled.rtvi_observer_params.user_llm_enabled is False


def test_session_config_rereads_between_sessions_without_mutating_prior_snapshot(
    bot_module, monkeypatch
):
    """SA-11(FR-3)：同进程内改 `.env` 的 `SCENARIO` 后再次 `load_config()`
    得到新模板；先前产出的 `Config`/`AssembledPipeline` 快照不受影响（frozen
    快照，无"部分字段已切"的中间状态）。"""
    old_cfg = bot_module.cfg
    assert old_cfg.template.id == "voice_chat"
    old_assembled = bot_module.assemble_pipeline(old_cfg, _FakeTransport())
    assert old_assembled.template.id == "voice_chat"

    monkeypatch.setenv("SCENARIO", "english_tutor")
    new_cfg = bot_module.load_config()
    assert new_cfg.template.id == "english_tutor"

    # 先前的快照/装配结果必须原封不动。
    assert old_cfg.template.id == "voice_chat"
    assert old_assembled.template.id == "voice_chat"


def test_error_attribution_processor_none_is_not_slow_failed(bot_module):
    """SA-14(FR-12,design §6.4 R8 派生)：`ErrorFrame(processor=None)`（框架
    内部无法归因来源时的样子）与非慢脑来源均走通用 `pipeline-error`，绝不能
    被误判成 `slow-brain-failed` 并向面板推消息。

    本卡最易踩的坑（design ADR-6）：判断式若漏了 `slow_llm is not None` 这半
    句，关闭态下 `slow_llm=None` 时 `frame.processor is slow_llm` 对
    `processor=None` 会算 `True`，把一次真实的"用户完全听不到声音"故障误报
    成"慢脑降级正常工作"。这里直接复刻关闭态的调用形态（`slow_llm`/
    `slow_material_filter` 均为 `None`），钉死该判断式。
    """
    handler = bot_module.make_pipeline_error_handler(None, None)
    worker = _FakeWorker()
    error_frame = ErrorFrame(error="boom", processor=None, fatal=False)

    with _capture_logs() as captured:
        asyncio.run(handler(worker, error_frame))

    assert any("pipeline-error" in m for m in captured), "processor=None 应打通用 pipeline-error"
    assert not any("slow-failed" in m for m in captured), (
        "processor=None 绝不能被误判成 slow-failed"
    )
    assert worker.queued == [], "processor=None 不应向面板 push 任何消息"


def test_dispatch_unaffected_by_dual_brain_off(bot_module):
    """SA-15(FR-12)：关闭态下派活不受影响——`injector` 仍在快脑链路头部
    （`fast_llm` 之前）；`fast_context.tools` 仍含两个派活 tool；
    `dispatch_worker`/`exec_worker` 仍返回。"""
    assembled = bot_module.assemble_pipeline(bot_module.cfg, _FakeTransport())

    processors = assembled.pipeline.processors
    injector_idx = processors.index(assembled.injector)
    fast_llm_idx = processors.index(assembled.fast_llm)
    assert injector_idx < fast_llm_idx, "injector 必须仍在快脑链路头部（fast_llm 之前）"

    tools_schema = assembled.fast_context.tools
    registered = {wrapper.function for wrapper in tools_schema.direct_functions}
    assert registered == {task_dispatch.dispatch_task, task_dispatch.get_task_status}, (
        "fast_context.tools 必须仍恰含两个派活工具"
    )

    assert assembled.dispatch_worker is not None
    assert assembled.exec_worker is not None


def test_scenario_log_line_uses_effective_stt_model_per_provider(bot_module, monkeypatch):
    """s6 review Important-1：`[scenario]` 观测行的 `stt=<provider>/<model>`
    段必须打各 provider 真实生效的模型名。`cfg.stt_model` 只被 soniox
    builder 消费——deepgram/assemblyai builder 各自硬编码自己的模型
    （B-3 硬约束不变，`_build_assemblyai_stt` 依旧不读 `cfg.stt_model`），
    `_effective_stt_model()` 只是给日志用的事实源，不传进任何 Service
    构造器。三种 provider 逐一核对，并在 deepgram 上核对真实打出的日志行。
    """
    cfg_soniox = bot_module.load_config()
    assert cfg_soniox.stt_provider == "soniox"
    assert bot_module._effective_stt_model(cfg_soniox) == cfg_soniox.stt_model, (
        "soniox 的生效模型就是 cfg.stt_model 本身"
    )

    monkeypatch.setenv("STT_PROVIDER", "deepgram")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-test-key")
    cfg_deepgram = bot_module.load_config()
    assert bot_module._effective_stt_model(cfg_deepgram) == "nova-3-general"
    assert bot_module._effective_stt_model(cfg_deepgram) != cfg_deepgram.stt_model, (
        "deepgram builder 不读 cfg.stt_model，生效模型必须与它不同"
    )

    monkeypatch.setenv("SCENARIO", "english_tutor")
    monkeypatch.delenv("STT_PROVIDER", raising=False)
    cfg_tutor = bot_module.load_config()
    assert cfg_tutor.stt_provider == "assemblyai"
    assert bot_module._effective_stt_model(cfg_tutor) == "universal-3-5-pro"
    assert bot_module._effective_stt_model(cfg_tutor) != cfg_tutor.stt_model, (
        "assemblyai builder 不读 cfg.stt_model，生效模型必须与它不同"
    )

    with _capture_logs() as captured:
        bot_module.assemble_pipeline(cfg_deepgram, _FakeTransport())
    assert any("stt=deepgram/nova-3-general" in line for line in captured), (
        "观测行必须打 deepgram 真实生效模型 nova-3-general，而不是 cfg.stt_model 的 soniox 档位名"
    )
