import streamlit as st
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
import json
from datetime import datetime

st.set_page_config(page_title="💬 챗봇", page_icon="💬")
st.title("💬 챗봇")

# ── 사이드바 설정 ─────────────────────────────────────────────
with st.sidebar:
    st.header("설정")

    # secrets.toml에 키가 있으면 자동 사용, 없으면 입력창 표시
    default_key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if default_key:
        openai_api_key = default_key
        st.success("API Key가 secrets에서 로드됐습니다.", icon="✅")
    else:
        openai_api_key = st.text_input("OpenAI API Key", type="password")

    model = st.selectbox(
        "모델 선택",
        ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        index=0,
    )

    system_prompt = st.text_area(
        "System Prompt",
        value="You are a helpful assistant.",
        height=150,
    )

    max_history = st.slider(
        "최대 대화 기록 수",
        min_value=4,
        max_value=40,
        value=20,
        step=2,
        help="오래된 메시지를 자동으로 잘라내 토큰 초과를 방지합니다.",
    )

    st.divider()

    if st.button("대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # ── 대화 내보내기 ──────────────────────────────────────────
    st.subheader("대화 내보내기")

    has_messages = bool(st.session_state.get("messages"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if has_messages:
        txt_lines = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}"
            for m in st.session_state.messages
        )
        st.download_button(
            "TXT로 저장",
            data=txt_lines,
            file_name=f"chat_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        json_data = json.dumps(
            st.session_state.messages, ensure_ascii=False, indent=2
        )
        st.download_button(
            "JSON으로 저장",
            data=json_data,
            file_name=f"chat_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.caption("대화 내용이 없습니다.")

# ── 메인 영역 ─────────────────────────────────────────────────
if not openai_api_key:
    st.info("왼쪽 사이드바에 OpenAI API Key를 입력하세요.", icon="🗝️")
else:
    client = OpenAI(api_key=openai_api_key)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("메시지를 입력하세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        trimmed = st.session_state.messages[-max_history:]
        api_messages = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in trimmed
        ]

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=api_messages,
                stream=True,
            )
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
            st.session_state.messages.append({"role": "assistant", "content": response})

        except AuthenticationError:
            st.error("API Key가 올바르지 않습니다. 사이드바에서 키를 확인해 주세요.", icon="🔑")
        except RateLimitError:
            st.error("요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.", icon="⏱️")
        except APIConnectionError:
            st.error("OpenAI 서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", icon="🌐")
        except APIStatusError as e:
            st.error(f"API 오류가 발생했습니다. (상태 코드: {e.status_code})", icon="⚠️")
