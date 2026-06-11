import streamlit as st
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
import json
from datetime import datetime

st.set_page_config(page_title="💬 챗봇", page_icon="💬", layout="wide")

# ── 커스텀 CSS ────────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 배경 */
.stApp {
    background: linear-gradient(135deg, #0F0F1A 0%, #1A1A2E 100%);
}

/* 채팅 컨테이너 */
.stChatMessage {
    border-radius: 16px !important;
    padding: 4px 8px !important;
    margin-bottom: 8px !important;
}

/* 사용자 메시지 버블 */
[data-testid="chat-message-container"]:has([data-testid="chatAvatarIcon-user"]) {
    background: linear-gradient(135deg, #2D1B69 0%, #3D2B79 100%) !important;
    border: 1px solid #7C5CBF55 !important;
    box-shadow: 0 4px 15px rgba(124, 92, 191, 0.2) !important;
}

/* 어시스턴트 메시지 버블 */
[data-testid="chat-message-container"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: linear-gradient(135deg, #1A1A2E 0%, #1E2240 100%) !important;
    border: 1px solid #4A4A8A44 !important;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3) !important;
}

/* 입력창 */
.stChatInputContainer {
    background: #1A1A2E !important;
    border-radius: 12px !important;
    border: 1px solid #7C5CBF55 !important;
}
.stChatInputContainer:focus-within {
    border-color: #7C5CBF !important;
    box-shadow: 0 0 0 2px rgba(124,92,191,0.25) !important;
}

/* 타이틀 */
h1 {
    background: linear-gradient(90deg, #A78BFA, #7C5CBF, #60A5FA);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2rem !important;
    font-weight: 700 !important;
}

/* 사이드바 */
[data-testid="stSidebar"] {
    background: #12122080 !important;
    border-right: 1px solid #7C5CBF33 !important;
}

/* 뱃지 스타일 */
.model-badge {
    display: inline-block;
    background: linear-gradient(90deg, #7C5CBF, #4A90D9);
    color: white;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.5px;
}

/* 통계 카드 */
.stat-card {
    background: #1E1E35;
    border: 1px solid #7C5CBF33;
    border-radius: 10px;
    padding: 10px 14px;
    margin: 4px 0;
    text-align: center;
}
.stat-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #A78BFA;
}
.stat-label {
    font-size: 0.7rem;
    color: #8888AA;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* 구분선 */
hr {
    border-color: #7C5CBF33 !important;
}

/* 버튼 */
.stButton > button {
    border-radius: 8px !important;
    border: 1px solid #7C5CBF55 !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    border-color: #7C5CBF !important;
    box-shadow: 0 0 10px rgba(124,92,191,0.3) !important;
    transform: translateY(-1px) !important;
}
</style>
""", unsafe_allow_html=True)

st.title("💬 챗봇")

# ── 사이드바 설정 ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

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
        height=120,
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

    # ── 실시간 통계 ────────────────────────────────────────────
    st.subheader("📊 대화 통계")

    messages = st.session_state.get("messages", [])
    msg_count = len(messages)
    user_count = sum(1 for m in messages if m["role"] == "user")
    char_count = sum(len(m["content"]) for m in messages)
    token_est = char_count // 4  # 간이 추정 (1토큰 ≈ 4자)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{msg_count}</div>
            <div class="stat-label">총 메시지</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{user_count}</div>
            <div class="stat-label">내 질문</div>
        </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">~{token_est:,}</div>
        <div class="stat-label">추정 토큰 사용량</div>
    </div>""", unsafe_allow_html=True)

    st.markdown(f'<div style="margin-top:8px; text-align:center"><span class="model-badge">🤖 {model}</span></div>', unsafe_allow_html=True)

    st.divider()

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # ── 대화 내보내기 ──────────────────────────────────────────
    st.subheader("💾 대화 내보내기")

    has_messages = bool(messages)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if has_messages:
        txt_lines = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}"
            for m in messages
        )
        st.download_button(
            "📄 TXT로 저장",
            data=txt_lines,
            file_name=f"chat_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        json_data = json.dumps(messages, ensure_ascii=False, indent=2)
        st.download_button(
            "📋 JSON으로 저장",
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
            st.caption(message.get("time", ""))

    if prompt := st.chat_input("메시지를 입력하세요..."):
        now = datetime.now().strftime("%H:%M")
        st.session_state.messages.append({"role": "user", "content": prompt, "time": now})
        with st.chat_message("user"):
            st.markdown(prompt)
            st.caption(now)

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
                reply_time = datetime.now().strftime("%H:%M")
                st.caption(reply_time)
            st.session_state.messages.append({"role": "assistant", "content": response, "time": reply_time})

        except AuthenticationError:
            st.error("API Key가 올바르지 않습니다. 사이드바에서 키를 확인해 주세요.", icon="🔑")
        except RateLimitError:
            st.error("요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.", icon="⏱️")
        except APIConnectionError:
            st.error("OpenAI 서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", icon="🌐")
        except APIStatusError as e:
            st.error(f"API 오류가 발생했습니다. (상태 코드: {e.status_code})", icon="⚠️")
