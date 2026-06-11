import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
import json
from datetime import datetime
import os

# st.stop() 전에 등록해야 Streamlit Cloud에서도 안정적으로 동작
_SPEECH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speech_component")
_speech_input = components.declare_component("speech_input", path=_SPEECH_DIR)

st.set_page_config(
    page_title="🍽️ 대전 맛집 챗봇",
    page_icon="🍽️",
    layout="wide",
)

st.markdown("""
<style>
.stApp {
    background: linear-gradient(160deg, #1A0D04 0%, #0F0700 100%);
}
[data-testid="stSidebar"] {
    background: #130900 !important;
    border-right: 1px solid rgba(249,115,22,0.2) !important;
}
h1 {
    background: linear-gradient(90deg, #FB923C, #F97316, #FBBF24);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
}
.stButton > button {
    border-radius: 10px !important;
    border: 1px solid rgba(249,115,22,0.35) !important;
    background: rgba(249,115,22,0.08) !important;
    color: #FB923C !important;
    transition: all 0.2s !important;
    text-align: left !important;
}
.stButton > button:hover {
    background: rgba(249,115,22,0.22) !important;
    border-color: #F97316 !important;
    box-shadow: 0 0 10px rgba(249,115,22,0.25) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stChatInput"] textarea {
    background: #1E0E03 !important;
    border: 1px solid rgba(249,115,22,0.3) !important;
    border-radius: 12px !important;
    color: #FDE8D0 !important;
}
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """당신은 대전 맛집 전문 AI 어시스턴트입니다.
대전 전 지역(유성구·서구·동구·중구·대덕구)의 식당을 잘 알고 있으며,
음식 종류·분위기·가격대·위치를 고려해 최적의 맛집을 추천해줍니다.

추천할 때는 아래 형식을 따르세요:
- 식당 이름과 위치(동·구 기준)
- 대표 메뉴와 가격대
- 분위기 및 특징
- 추천 이유

성심당, 유성온천, 둔산동, 은행동, 대전역 인근 등 주요 지역 정보를 잘 알고 있습니다.
한국어로 친절하고 구체적으로 답변하세요."""

QUICK_PROMPTS = [
    ("🍜", "오늘 뭐 먹지?", "오늘 대전에서 뭐 먹으면 좋을지 기분에 맞게 추천해줘"),
    ("📍", "둔산동 맛집", "둔산동에서 가볼 만한 맛집 추천해줘"),
    ("🥐", "성심당 근처", "성심당 근처에서 식사할 수 있는 맛집 알려줘"),
    ("👫", "데이트 코스", "대전에서 데이트하기 좋은 분위기 있는 맛집 코스 짜줘"),
    ("🍺", "혼술·혼밥", "혼자 가기 부담 없는 대전 맛집 추천해줘"),
    ("💸", "가성비 맛집", "대전에서 저렴하고 맛있는 가성비 식당 알려줘"),
]

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🍽️ 대전 맛집 챗봇")
    st.caption("대전 구석구석 맛집을 찾아드립니다")
    st.divider()

    default_key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if default_key:
        openai_api_key = default_key
        st.success("API Key 로드됨", icon="✅")
    else:
        openai_api_key = st.text_input("OpenAI API Key", type="password")

    st.divider()

    st.markdown("**⚡ 빠른 질문**")
    for emoji, label, prompt in QUICK_PROMPTS:
        if st.button(f"{emoji} {label}", use_container_width=True, key=f"quick_{label}"):
            st.session_state.pending_prompt = prompt

    st.divider()

    with st.expander("⚙️ 고급 설정"):
        model = st.selectbox(
            "모델",
            ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
            index=0,
        )
        max_history = st.slider("최대 대화 기록 수", 4, 40, 20, 2,
                                help="오래된 메시지를 잘라내 토큰 초과를 방지합니다.")

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    has_messages = bool(st.session_state.get("messages"))
    if has_messages:
        st.divider()
        st.markdown("**💾 대화 내보내기**")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        messages = st.session_state.messages

        txt_lines = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}" for m in messages
        )
        st.download_button("📄 TXT", data=txt_lines,
                           file_name=f"daejeon_chat_{timestamp}.txt",
                           mime="text/plain", use_container_width=True)
        json_data = json.dumps(messages, ensure_ascii=False, indent=2)
        st.download_button("📋 JSON", data=json_data,
                           file_name=f"daejeon_chat_{timestamp}.json",
                           mime="application/json", use_container_width=True)

# ── 메인 영역 ─────────────────────────────────────────────────
st.title("🍽️ 대전 맛집 챗봇")
st.caption("대전 어디든, 어떤 음식이든 — 딱 맞는 맛집을 찾아드립니다 🗺️")

if not openai_api_key:
    st.info("왼쪽 사이드바에 OpenAI API Key를 입력하세요.", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "model" not in st.session_state:
    st.session_state.model = "gpt-4o"
if "_last_voice" not in st.session_state:
    st.session_state._last_voice = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── 음성 입력 ──────────────────────────────────────────────────
with st.expander("🎤 음성으로 질문하기", expanded=False):
    st.caption("말하고 정지하면 자동으로 전송됩니다 · Chrome/Edge 전용")
    voice_text = _speech_input(key="voice", default=None)
    if voice_text and voice_text != st.session_state._last_voice:
        st.session_state._last_voice = voice_text
        st.session_state.pending_prompt = voice_text
        st.rerun()

# 빠른 질문 버튼 또는 직접 입력 처리
user_input = st.chat_input("대전 맛집을 물어보세요! (예: 유성구 삼겹살 추천해줘)")

prompt = st.session_state.pending_prompt or user_input
if st.session_state.pending_prompt:
    st.session_state.pending_prompt = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    trimmed = st.session_state.messages[-max_history:]
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
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
