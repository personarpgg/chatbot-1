import streamlit as st
from openai import OpenAI
import json
from datetime import datetime

st.set_page_config(page_title="💬 Chatbot", page_icon="💬")
st.title("💬 Chatbot")

# ── 사이드바 설정 ─────────────────────────────────────────────
with st.sidebar:
    st.header("설정")

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

        # 토큰 초과 방지: 최근 max_history 개 메시지만 API에 전송
        trimmed = st.session_state.messages[-max_history:]
        api_messages = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in trimmed
        ]

        stream = client.chat.completions.create(
            model=model,
            messages=api_messages,
            stream=True,
        )

        with st.chat_message("assistant"):
            response = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": response})
