import json
import os
import pprint
import re
from datetime import datetime
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="UE 材质分析器", layout="wide")
st.title("UE 材质分析器")

PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.normpath(os.path.join(PYTHON_DIR, "..", ".."))
SKILL_EXPORT_DIR = os.path.join(PLUGIN_ROOT, "Skills")
APPDATA_ROOT = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
USER_CONFIG_DIR = os.path.join(APPDATA_ROOT, "MaterialAnalyzer")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "ai_config.json")

COMMON_AI_ENDPOINTS = {
    "302": "https://api.302.ai/v1",
    "302.ai": "https://api.302.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openrouter.ai": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "google gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "gemini official": "https://generativelanguage.googleapis.com/v1beta/openai",
}

query_params = st.query_params
query_material = str(query_params.get("material_name", "")).strip()


def _load_user_ai_config() -> dict:
    if not os.path.exists(USER_CONFIG_PATH):
        return {}

    try:
        with open(USER_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _save_user_ai_config(config: dict) -> None:
    os.makedirs(USER_CONFIG_DIR, exist_ok=True)
    with open(USER_CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)


def normalize_ai_endpoint(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""

    lowered = raw.lower().strip()
    if lowered in COMMON_AI_ENDPOINTS:
        return COMMON_AI_ENDPOINTS[lowered]

    normalized = raw.replace("\\", "/")
    normalized = re.sub(r"/chat/completions/?$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"/responses/?$", "", normalized, flags=re.IGNORECASE)

    if normalized.lower() in COMMON_AI_ENDPOINTS:
        return COMMON_AI_ENDPOINTS[normalized.lower()]

    if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        normalized = "https://" + normalized.lstrip("/")

    return normalized.rstrip("/")


def _persist_sidebar_ai_config() -> None:
    current = _load_user_ai_config()

    endpoint = normalize_ai_endpoint(st.session_state.get("ai_endpoint_input", ""))
    model = str(st.session_state.get("ai_model_input", "")).strip()
    api_key = str(st.session_state.get("api_key_input", "")).strip()

    if endpoint:
        current["endpoint"] = endpoint
    if model:
        current["model"] = model
    if api_key:
        current["api_key"] = api_key

    _save_user_ai_config(current)


user_ai_config = _load_user_ai_config()
saved_api_base = normalize_ai_endpoint(str(user_ai_config.get("endpoint", "")))
saved_ai_model = str(user_ai_config.get("model", "")).strip()
saved_api_key = str(user_ai_config.get("api_key", "")).strip()

st.session_state.setdefault("ai_endpoint_input", "")
st.session_state.setdefault("ai_model_input", "")
st.session_state.setdefault("api_key_input", saved_api_key)


with st.sidebar:
    st.header("连接设置")
    bridge_url = "http://127.0.0.1:30010"
    auto_follow_selected = st.toggle("自动读取 UE 当前选择材质", value=True)
    material_path = st.text_input("材质路径（可选）", value=query_material)
    fetch_by_path = st.button("按路径读取")

    st.divider()
    st.header("AI 分析配置")
    env_api_base = os.getenv("OPENAI_BASE_URL", "")
    st_api_base = ""
    try:
        st_api_base = str(st.secrets.get("OPENAI_BASE_URL", ""))
    except Exception:
        st_api_base = ""

    default_ai_endpoint = normalize_ai_endpoint(saved_api_base or st_api_base or env_api_base or "https://api.302.ai/v1")
    if not st.session_state.get("ai_endpoint_input"):
        st.session_state["ai_endpoint_input"] = default_ai_endpoint

    ai_endpoint = st.text_input(
        "OpenAI 兼容端点地址",
        key="ai_endpoint_input",
        on_change=_persist_sidebar_ai_config,
        help="可输入完整的 OpenAI 兼容端点地址，也可直接输入 gemini、openrouter、302.ai 等常见平台名。",
    )
    ai_endpoint = normalize_ai_endpoint(ai_endpoint)
    if st.session_state.get("ai_endpoint_input", "").strip() and ai_endpoint != st.session_state.get("ai_endpoint_input", "").strip():
        st.caption(f"将按规范地址使用：{ai_endpoint}")

    default_ai_model = saved_ai_model or "gemini-3-flash-preview"
    if not st.session_state.get("ai_model_input"):
        st.session_state["ai_model_input"] = default_ai_model

    ai_model = st.text_input("模型名", key="ai_model_input", on_change=_persist_sidebar_ai_config)
    ai_timeout = 45
    ai_temperature = 0.2

    env_api_key = os.getenv("OPENAI_API_KEY", "")
    st_api_key = ""
    try:
        st_api_key = str(st.secrets.get("OPENAI_API_KEY", ""))
    except Exception:
        st_api_key = ""

    api_key_input = st.text_input(
        "API Key（首次填写后自动复用）",
        key="api_key_input",
        type="password",
        on_change=_persist_sidebar_ai_config,
    )
    st.caption("请输入 OpenAI 兼容协议端点；可直接使用 gemini、OpenRouter、302.ai 等提供兼容接口的平台。")


def fetch_json(url: str) -> dict:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {
            "ok": False,
            "error_type": "request_failed",
            "message": str(exc),
        }


def resolve_api_key(user_input: str, secret_key: str, env_key: str) -> str:
    key = (user_input or "").strip()
    if key:
        return key
    key = saved_api_key.strip()
    if key:
        return key
    key = (secret_key or "").strip()
    if key:
        return key
    return (env_key or "").strip()


def validate_api_key(key: str) -> tuple[bool, str]:
    if not key:
        return False, "API 未配置"
    if len(key) < 20:
        return False, "API 配置异常"
    return True, "API 已就绪"


def build_endpoint(base: str, path: str) -> str:
    base = base.rstrip("/")
    if path:
        return f"{base}/material_export_with_fallback?path={quote(path, safe='')}"
    return f"{base}/selected_material_summary"


def normalize(result: dict) -> dict:
    material = result.get("material") or {}
    nodes = result.get("nodes") or []
    edges = result.get("edges") or []
    bindings = result.get("property_bindings") or result.get("outputs") or []
    comments = result.get("comments") or []
    stats = result.get("stats") or {}

    if not stats:
        stats = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "binding_count": len(bindings),
            "comment_count": len(comments),
        }

    return {
        "ok": bool(result.get("ok", False)),
        "source_type": result.get("source_type") or result.get("source") or "unknown",
        "resolved_material_path": result.get("resolved_material_path") or "",
        "selected_material_path": result.get("selected_material_path") or "",
        "cpp_attempted": bool(result.get("cpp_attempted", False)),
        "cpp_ok": bool(result.get("cpp_ok", False)),
        "fallback_from": result.get("fallback_from") or "",
        "fallback_reason": result.get("fallback_reason") or "",
        "fallback_message": result.get("fallback_message") or "",
        "material": material,
        "nodes": nodes,
        "edges": edges,
        "property_bindings": bindings,
        "comments": comments,
        "stats": stats,
        "raw": result,
    }


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value or "")
    cleaned = cleaned.strip("_")
    return cleaned or "material"


def _to_snake_case(value: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value or "")
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", normalized)
    normalized = normalized.strip("_").lower()
    return normalized or "rule"


def _build_rule_entry(rule: dict, index: int) -> dict:
    rule_name = str(rule.get("rule_name") or f"Rule_{index + 1}").strip()
    severity = str(rule.get("severity") or "medium").strip().lower() or "medium"
    return {
        "rule_id": _to_snake_case(rule_name),
        "rule_name": rule_name,
        "severity": severity,
        "trigger": str(rule.get("trigger") or "").strip(),
        "check_logic": str(rule.get("check_logic") or "").strip(),
        "fix_strategy": str(rule.get("fix_strategy") or "").strip(),
    }


def _build_applies_to(material_path: str, material_name: str) -> dict:
    path_segments = [segment for segment in material_path.split("/") if segment]
    tags = []
    for segment in path_segments:
        lower_segment = segment.lower()
        if lower_segment not in tags:
            tags.append(lower_segment)

    return {
        "material_paths": [material_path] if material_path else [],
        "material_names": [material_name] if material_name else [],
        "tags": tags,
    }


def export_skill_script(report: dict, material_path: str) -> str:
    skill_rules = report.get("skills_rules") or []
    if not skill_rules:
        return ""

    os.makedirs(SKILL_EXPORT_DIR, exist_ok=True)

    material_name = material_path.split("/")[-1] if material_path else "material"
    material_name = material_name.split(".")[-1] if "." in material_name else material_name
    skill_id = _to_snake_case(material_name)
    file_name = f"{_sanitize_filename(material_name)}_skill_module.py"
    file_path = os.path.join(SKILL_EXPORT_DIR, file_name)

    payload = {
        "skill_id": skill_id,
        "skill_name": f"{material_name} Formal Skill Module",
        "version": "1.0.0",
        "enabled": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "material_path": material_path,
        "description": "AI-generated reusable material analysis skill module.",
        "applies_to": _build_applies_to(material_path, material_name),
        "rules": [_build_rule_entry(rule, index) for index, rule in enumerate(skill_rules)],
    }

    content = (
        "# Auto-generated formal skill module\n"
        "SKILL_MODULE = " + pprint.pformat(payload, sort_dicts=False, width=100, compact=False) + "\n"
    )

    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write(content)

    return file_path


def _extract_json_from_text(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        return json.loads(match.group(0))

    raise ValueError("模型返回内容不是有效 JSON")


def call_llm_analysis(
    endpoint: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
    temperature: float,
    payload: dict,
) -> dict:
    graph_for_model = {
        "material": payload.get("material") or {},
        "stats": payload.get("stats") or {},
        "nodes": (payload.get("nodes") or [])[:180],
        "edges": (payload.get("edges") or [])[:260],
        "property_bindings": (payload.get("property_bindings") or [])[:100],
        "comments": (payload.get("comments") or [])[:40],
    }

    system_prompt = (
        "你是 Unreal Engine 材质性能分析专家。"
        "请直接基于提供的材质图数据进行分析，重点关注连接合理性、重复计算、纹理采样预算、UV 逻辑、打包机会和优化优先级。"
        "你必须严格返回一个 JSON 对象。"
        "所有字段内容都必须使用简体中文表达。"
        "不要输出 markdown，不要输出代码块，不要输出 JSON 之外的解释。"
    )

    user_prompt = {
        "task": "分析这个 UE 材质图，并输出结构化优化报告。",
        "analysis_focus": [
            "整体复杂度与主要性能风险",
            "连接质量与可疑图结构",
            "重复计算与镜像逻辑",
            "纹理采样预算与通道打包机会",
            "UV 逻辑复用与 Material Function 抽取机会",
            "按优先级排序的优化动作",
            "可复用的 Skills 规则",
        ],
        "required_output_schema": {
            "overall_assessment": "string，必须是中文总结",
            "connection_findings": [
                {
                    "severity": "high|medium|low",
                    "node_ids": ["string，节点 ID 原样保留"],
                    "problem": "string，中文问题标题",
                    "reason": "string，中文原因说明",
                    "suggestion": "string，中文建议",
                }
            ],
            "redundancy_findings": [
                {
                    "severity": "high|medium|low",
                    "node_ids": ["string，节点 ID 原样保留"],
                    "pattern": "string，中文冗余模式标题",
                    "evidence": "string，中文依据说明",
                    "suggestion": "string，中文建议",
                }
            ],
            "optimization_actions": [
                {
                    "priority": "P0|P1|P2",
                    "action": "string，中文动作标题",
                    "expected_gain": "string，中文收益说明",
                }
            ],
            "skills_rules": [
                {
                    "rule_name": "string，规则名可英文或中文",
                    "trigger": "string，中文触发条件",
                    "check_logic": "string，中文检查逻辑",
                    "fix_strategy": "string，中文修复策略",
                }
            ],
        },
        "material_graph": graph_for_model,
    }

    url = endpoint.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {
            "ok": False,
            "error_type": "llm_request_failed",
            "message": str(exc),
        }

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return {
            "ok": False,
            "error_type": "llm_response_invalid",
            "message": "Model response missing choices.message.content",
            "raw": data,
        }

    try:
        parsed = _extract_json_from_text(str(content))
        return {
            "ok": True,
            "report": parsed,
            "raw_content": content,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_type": "llm_json_parse_failed",
            "message": str(exc),
            "raw_content": content,
        }


def _severity_label(severity: str) -> str:
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }
    return mapping.get(str(severity).lower(), str(severity or "-"))


def _render_finding_cards(items: list[dict], kind: str) -> None:
    if not items:
        st.caption("无")
        return

    for index, item in enumerate(items, start=1):
        severity = _severity_label(item.get("severity", ""))
        node_ids = item.get("node_ids") or []
        node_text = ", ".join(node_ids) if node_ids else "-"

        if kind == "connection":
            title = item.get("problem") or f"问题 {index}"
            reason = item.get("reason") or "-"
            suggestion = item.get("suggestion") or "-"
            with st.container(border=True):
                st.markdown(f"**{index}. {title}**")
                st.caption(f"严重级别：{severity} | 相关节点：{node_text}")
                st.write(f"原因：{reason}")
                st.write(f"建议：{suggestion}")
        elif kind == "redundancy":
            title = item.get("pattern") or f"问题 {index}"
            evidence = item.get("evidence") or "-"
            suggestion = item.get("suggestion") or "-"
            with st.container(border=True):
                st.markdown(f"**{index}. {title}**")
                st.caption(f"严重级别：{severity} | 相关节点：{node_text}")
                st.write(f"依据：{evidence}")
                st.write(f"建议：{suggestion}")


def _render_action_cards(items: list[dict]) -> None:
    if not items:
        st.caption("无")
        return

    for index, item in enumerate(items, start=1):
        priority = item.get("priority") or "-"
        action = item.get("action") or f"动作 {index}"
        expected_gain = item.get("expected_gain") or "-"
        with st.container(border=True):
            st.markdown(f"**{index}. {action}**")
            st.caption(f"优先级：{priority}")
            st.write(f"预期收益：{expected_gain}")


def render_ai_report(report: dict) -> None:
    overall = str(report.get("overall_assessment") or "").strip()
    if overall:
        st.markdown("**总体结论**")
        st.info(overall)

    st.markdown("**连接问题**")
    _render_finding_cards(report.get("connection_findings") or [], "connection")

    st.markdown("**冗余问题**")
    _render_finding_cards(report.get("redundancy_findings") or [], "redundancy")

    st.markdown("**优化动作**")
    _render_action_cards(report.get("optimization_actions") or [])


if fetch_by_path:
    query_path = material_path.strip()
    endpoint = build_endpoint(bridge_url, query_path)
    payload = normalize(fetch_json(endpoint))
    st.session_state["analysis_payload"] = payload

if auto_follow_selected and not material_path.strip():
    @st.fragment(run_every="2s")
    def _poll_selected_material() -> None:
        endpoint = build_endpoint(bridge_url, "")
        polled_payload = normalize(fetch_json(endpoint))

        if polled_payload.get("ok"):
            current_selected = polled_payload.get("resolved_material_path") or polled_payload.get("selected_material_path")
            previous_selected = st.session_state.get("_last_selected_material", "")
            if current_selected and (
                current_selected != previous_selected or "analysis_payload" not in st.session_state
            ):
                st.session_state["analysis_payload"] = polled_payload
                st.session_state["_last_selected_material"] = current_selected
                st.rerun()
        elif "analysis_payload" not in st.session_state:
            st.session_state["analysis_payload"] = polled_payload
            st.rerun()

    _poll_selected_material()

if query_material and "analysis_payload" not in st.session_state:
    endpoint = build_endpoint(bridge_url, query_material)
    payload = normalize(fetch_json(endpoint))
    st.session_state["analysis_payload"] = payload

payload = st.session_state.get("analysis_payload")

resolved_api_key = resolve_api_key(api_key_input, st_api_key, env_api_key)
api_key_ok, api_key_msg = validate_api_key(resolved_api_key)

with st.sidebar:
    if api_key_ok:
        st.success(api_key_msg)
    else:
        st.warning(api_key_msg)

if not api_key_ok:
    st.error("API 不可用时，本工具不会执行本地材质分析。请先配置可用的 API Key。")
    st.stop()
elif not payload:
    st.info("请先在 UE 中选中材质（自动读取），或输入材质路径后点击“按路径读取”。")
else:
    if not payload["ok"]:
        st.error(f"读取失败：{payload['raw'].get('error_type', 'unknown')} - {payload['raw'].get('message', '')}")
    else:
        material = payload.get("material") or {}
        material_name = material.get("name") or payload.get("resolved_material_path") or payload.get("selected_material_path") or "未命名材质"
        st.success(f"当前材质：{material_name}")
        material_path = material.get("path") or payload.get("resolved_material_path") or payload.get("selected_material_path") or ""
        if material_path:
            st.caption(f"材质路径：{material_path}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("节点", payload["stats"].get("node_count", 0))
        c2.metric("连线", payload["stats"].get("edge_count", 0))
        c3.metric("输出通道", payload["stats"].get("binding_count", 0))
        c4.metric("注释", payload["stats"].get("comment_count", 0))

        material = payload["material"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("材质域", material.get("domain", "") or "-")
        m2.metric("混合模式", material.get("blend_mode", "") or "-")
        m3.metric("着色模型", material.get("shading_model", "") or "-")
        m4.metric("双面", "是" if material.get("two_sided", False) else "否")

        st.subheader("AI 分析")
        run_ai_first_btn = st.button("AI 分析当前材质", type="primary", use_container_width=True)
        if run_ai_first_btn:
            if not api_key_ok:
                st.error("运行 AI 分析前请先配置可用的 API Key。")
            else:
                with st.spinner("正在调用模型分析当前材质图..."):
                    llm_result = call_llm_analysis(
                        endpoint=ai_endpoint,
                        api_key=resolved_api_key,
                        model=ai_model,
                        timeout_seconds=int(ai_timeout),
                        temperature=float(ai_temperature),
                        payload=payload,
                    )

                skill_export_path = ""
                if llm_result.get("ok"):
                    skill_export_path = export_skill_script(
                        llm_result.get("report") or {},
                        payload.get("resolved_material_path") or payload.get("selected_material_path") or "",
                    )

                st.session_state["llm_analysis_result"] = llm_result
                st.session_state["final_analysis_report"] = {
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "material_path": payload.get("resolved_material_path") or payload.get("selected_material_path") or "",
                    "material_summary": {
                        "name": material.get("name", ""),
                        "path": material.get("path", ""),
                        "domain": material.get("domain", ""),
                        "blend_mode": material.get("blend_mode", ""),
                        "shading_model": material.get("shading_model", ""),
                        "two_sided": material.get("two_sided", False),
                    },
                    "stats": payload.get("stats") or {},
                    "skill_export_path": skill_export_path,
                    "llm_result": llm_result,
                }

        llm_result = st.session_state.get("llm_analysis_result")
        if llm_result:
            if llm_result.get("ok"):
                skill_export_path = ""
                final_report = st.session_state.get("final_analysis_report") or {}
                if isinstance(final_report, dict):
                    skill_export_path = str(final_report.get("skill_export_path") or "").strip()

                if skill_export_path:
                    st.success(f"AI 分析完成，Skill 已生成：{skill_export_path}")
                else:
                    st.success("AI 分析完成")

                render_ai_report(llm_result.get("report") or {})
            else:
                st.error(f"AI 分析失败：{llm_result.get('error_type', 'unknown')} - {llm_result.get('message', '')}")
                if llm_result.get("raw_content"):
                    with st.expander("模型原始返回", expanded=True):
                        st.code(str(llm_result.get("raw_content")), language="text")
        else:
            st.info("点击上方按钮后，将直接把当前材质结构化信息发送给 AI，并按固定分析维度输出报告。")
        with st.expander("详细材质信息", expanded=False):
            n_col, e_col = st.columns(2)

            with n_col:
                st.subheader("节点")
                if payload["nodes"]:
                    node_df = pd.DataFrame(payload["nodes"])
                    st.dataframe(node_df, use_container_width=True)
                else:
                    st.warning("暂无节点")

            with e_col:
                st.subheader("连线")
                if payload["edges"]:
                    edge_df = pd.DataFrame(payload["edges"])
                    st.dataframe(edge_df, use_container_width=True)
                else:
                    st.warning("暂无连线")

            b_col, c_col = st.columns(2)

            with b_col:
                st.subheader("输出通道")
                if payload["property_bindings"]:
                    bind_df = pd.DataFrame(payload["property_bindings"])
                    st.dataframe(bind_df, use_container_width=True)
                else:
                    st.warning("暂无输出通道")

            with c_col:
                st.subheader("注释")
                if payload["comments"]:
                    comment_df = pd.DataFrame(payload["comments"])
                    st.dataframe(comment_df, use_container_width=True)
                else:
                    st.warning("暂无注释")

            with st.expander("原始 JSON", expanded=False):
                st.code(json.dumps(payload["raw"], ensure_ascii=False, indent=2), language="json")

        llm_result = st.session_state.get("llm_analysis_result")
        final_report = st.session_state.get("final_analysis_report")

        if final_report:
            with st.expander("最终结构化报告", expanded=False):
                st.code(json.dumps(final_report, ensure_ascii=False, indent=2), language="json")
