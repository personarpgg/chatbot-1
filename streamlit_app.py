import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
import json, re
from datetime import datetime
import os, base64
import folium
from streamlit_folium import st_folium

# ── 컴포넌트 등록 (st.stop() 전에) ───────────────────────────────
_SPEECH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speech_component")
_speech_input = components.declare_component("speech_input", path=_SPEECH_DIR)

st.set_page_config(page_title="🍽️ 대전 맛집 챗봇", page_icon="🍽️", layout="wide")

st.markdown("""
<style>
.stApp { background: linear-gradient(160deg, #1A0D04 0%, #0F0700 100%); }
[data-testid="stSidebar"] { background: #130900 !important; border-right: 1px solid rgba(249,115,22,0.2) !important; }
h1 { background: linear-gradient(90deg, #FB923C, #F97316, #FBBF24); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800 !important; }
.stButton > button { border-radius: 10px !important; border: 1px solid rgba(249,115,22,0.35) !important; background: rgba(249,115,22,0.08) !important; color: #FB923C !important; transition: all 0.2s !important; text-align: left !important; }
.stButton > button:hover { background: rgba(249,115,22,0.22) !important; border-color: #F97316 !important; box-shadow: 0 0 10px rgba(249,115,22,0.25) !important; transform: translateY(-1px) !important; }
div[data-testid="stChatInput"] textarea { background: #1E0E03 !important; border: 1px solid rgba(249,115,22,0.3) !important; border-radius: 12px !important; color: #FDE8D0 !important; }
</style>
""", unsafe_allow_html=True)

# ── 상수 ──────────────────────────────────────────────────────────
DAEJEON_CENTER = [36.3504, 127.3845]
VISION_MODELS  = {"gpt-4o", "gpt-4o-mini"}
PLACES_RE      = re.compile(r'<!--PLACES_DATA\s*(.*?)\s*PLACES_DATA-->', re.DOTALL)

SYSTEM_PROMPT = """당신은 대전 맛집 전문 AI 어시스턴트입니다.
대전 전 지역(유성구·서구·동구·중구·대덕구)의 식당을 잘 알고 있으며,
음식 종류·분위기·가격대·위치를 고려해 최적의 맛집을 추천해줍니다.

사진이 첨부된 경우, 사진 속 음식이나 장소를 분석해 대전에서 비슷한 음식을 맛볼 수 있는 식당을 추천해주세요.

추천할 때는 아래 형식을 따르세요:
- 식당 이름과 위치(동·구 기준)
- 대표 메뉴와 가격대
- 분위기 및 특징
- 추천 이유
- 예상 별점 (5점 만점)

성심당, 유성온천, 둔산동, 은행동, 대전역 인근 등 주요 지역 정보를 잘 알고 있습니다.

★★ 중요 ★★ 식당을 추천할 때는 반드시 응답 마지막에 아래 JSON 블록을 추가하세요.
이 블록은 지도 표시에 사용되며, 사용자에게는 텍스트로 표시되지 않습니다.
lat/lng는 대전 내 실제 위치에 최대한 정확한 소수점 4자리 좌표를 입력하세요.

<!--PLACES_DATA
{"places":[{"name":"식당명","address":"대전 구 동 상세주소","lat":36.0000,"lng":127.0000,"category":"음식종류","price_range":"10,000-20,000원","rating_est":4.3,"desc":"한줄소개"}]}
PLACES_DATA-->

한국어로 친절하고 구체적으로 답변하세요."""

QUICK_PROMPTS = [
    ("🍜", "오늘 뭐 먹지?", "오늘 대전에서 뭐 먹으면 좋을지 기분에 맞게 추천해줘"),
    ("📍", "둔산동 맛집", "둔산동에서 가볼 만한 맛집 추천해줘"),
    ("🥐", "성심당 근처", "성심당 근처에서 식사할 수 있는 맛집 알려줘"),
    ("👫", "데이트 코스", "대전에서 데이트하기 좋은 분위기 있는 맛집 코스 짜줘"),
    ("🍺", "혼술·혼밥", "혼자 가기 부담 없는 대전 맛집 추천해줘"),
    ("💸", "가성비 맛집", "대전에서 저렴하고 맛있는 가성비 식당 알려줘"),
]

# ── 유틸 ──────────────────────────────────────────────────────────
def parse_places(text: str):
    m = PLACES_RE.search(text)
    if not m:
        return text, []
    try:
        places = json.loads(m.group(1)).get("places", [])
    except Exception:
        places = []
    return PLACES_RE.sub("", text).strip(), places

def make_map(places, saved_names=None):
    saved_names = saved_names or set()
    m = folium.Map(location=DAEJEON_CENTER, zoom_start=13, tiles="CartoDB positron")
    for p in places:
        lat, lng = p.get("lat"), p.get("lng")
        if not lat or not lng:
            continue
        saved = p["name"] in saved_names
        popup_html = (
            f"<div style='min-width:160px;font-family:sans-serif'>"
            f"<b style='font-size:13px'>{p['name']}</b><br>"
            f"<span style='color:#555;font-size:11px'>{p.get('address','')}</span><br>"
            f"⭐ {p.get('rating_est','?')}/5 &nbsp;·&nbsp; {p.get('category','')}<br>"
            f"💰 {p.get('price_range','')}<br>"
            f"<i style='font-size:11px'>{p.get('desc','')}</i>"
            f"</div>"
        )
        folium.Marker(
            [lat, lng],
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=("⭐ " if saved else "") + p["name"],
            icon=folium.Icon(color="orange" if saved else "blue"),
        ).add_to(m)
    return m

def _text(c):
    if isinstance(c, list):
        t = " ".join(p["text"] for p in c if p.get("type") == "text")
        return t + (" [이미지 첨부]" if any(p.get("type") == "image_url" for p in c) else "")
    return c

# ── 사이드바 ──────────────────────────────────────────────────────
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
    for emoji, label, qp in QUICK_PROMPTS:
        if st.button(f"{emoji} {label}", use_container_width=True, key=f"quick_{label}"):
            st.session_state.pending_prompt = qp
    st.divider()

    with st.expander("⚙️ 고급 설정"):
        model = st.selectbox("모델", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], index=0)
        max_history = st.slider("최대 대화 기록 수", 4, 40, 20, 2,
                                help="오래된 메시지를 잘라내 토큰 초과를 방지합니다.")

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_places = []
        st.rerun()

    if st.session_state.get("messages"):
        st.divider()
        st.markdown("**💾 대화 내보내기**")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        msgs = st.session_state.messages
        txt = "\n\n".join(f"[{m['role'].upper()}]\n{_text(m['content'])}" for m in msgs)
        st.download_button("📄 TXT", data=txt,
                           file_name=f"daejeon_chat_{ts}.txt", mime="text/plain",
                           use_container_width=True)
        st.download_button("📋 JSON", data=json.dumps(msgs, ensure_ascii=False, indent=2),
                           file_name=f"daejeon_chat_{ts}.json", mime="application/json",
                           use_container_width=True)

# ── 메인 ──────────────────────────────────────────────────────────
st.title("🍽️ 대전 맛집 챗봇")
st.caption("대전 어디든, 어떤 음식이든 — 딱 맞는 맛집을 찾아드립니다 🗺️")

if not openai_api_key:
    st.info("왼쪽 사이드바에 OpenAI API Key를 입력하세요.", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

for _k, _v in [
    ("messages", []), ("pending_prompt", None), ("_last_voice", None),
    ("_img_bytes", None), ("_img_mime", None), ("_img_key", 0),
    ("my_places", []), ("last_places", []), ("plan_result", None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

saved_names = {p["name"] for p in st.session_state.my_places}

# ── 탭 ───────────────────────────────────────────────────────────
tab_chat, tab_mymap, tab_plan = st.tabs(["💬 채팅 & 지도", "⭐ 나만의 지도", "📅 코스 계획"])

# ──────────────────────────────────────────────────────────────────
with tab_chat:

    # 채팅 기록 표시
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            c = msg["content"]
            if isinstance(c, list):
                for part in c:
                    if part["type"] == "text":
                        st.markdown(part["text"])
                    elif part["type"] == "image_url":
                        _, b64 = part["image_url"]["url"].split(",", 1)
                        st.image(base64.b64decode(b64), width=280)
            else:
                st.markdown(c)

    # 최근 추천 지도
    if st.session_state.last_places:
        with st.expander("🗺️ 추천 맛집 지도", expanded=True):
            m_chat = make_map(st.session_state.last_places, saved_names)
            st_folium(m_chat, width="100%", height=380, returned_objects=[])
            st.caption("마커 클릭 시 상세정보 · 주황색 = 저장됨")

            ncols = min(len(st.session_state.last_places), 3)
            cols = st.columns(ncols)
            for i, p in enumerate(st.session_state.last_places):
                with cols[i % ncols]:
                    st.markdown(f"**{p['name']}**")
                    st.caption(
                        f"⭐ {p.get('rating_est','?')}/5 · {p.get('category','')}\n"
                        f"💰 {p.get('price_range','')}\n"
                        f"📍 {p.get('address','')}"
                    )
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        saved = p["name"] in saved_names
                        lbl = "✅ 저장됨" if saved else "⭐ 저장"
                        if st.button(lbl, key=f"save_chat_{i}", use_container_width=True):
                            if saved:
                                st.session_state.my_places = [
                                    x for x in st.session_state.my_places if x["name"] != p["name"]
                                ]
                            else:
                                st.session_state.my_places.append(p)
                            st.rerun()
                    with bc2:
                        st.link_button(
                            "🗺️ 카카오맵",
                            f"https://map.kakao.com/?q={p.get('address', p['name'])}",
                            use_container_width=True,
                        )

    # 음성 입력
    with st.expander("🎤 음성으로 질문하기", expanded=False):
        st.caption("말하고 정지하면 자동으로 전송됩니다 · Chrome/Edge 전용")
        voice_text = _speech_input(key="voice", default=None)
        if voice_text and voice_text != st.session_state._last_voice:
            st.session_state._last_voice = voice_text
            st.session_state.pending_prompt = voice_text

    # 이미지 업로드
    uploaded = st.file_uploader(
        "📷 음식 사진 첨부",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"img_{st.session_state._img_key}",
        label_visibility="collapsed",
    )
    if uploaded:
        raw = uploaded.read()
        if raw:
            st.session_state._img_bytes = raw
            st.session_state._img_mime = uploaded.type or "image/jpeg"
        if st.session_state._img_bytes:
            if model not in VISION_MODELS:
                st.warning("이미지 인식은 gpt-4o / gpt-4o-mini 모델만 지원합니다.", icon="⚠️")
            else:
                st.image(st.session_state._img_bytes, width=220)
                st.caption("💬 아래 채팅창에 질문을 입력하고 전송하세요")
    else:
        st.session_state._img_bytes = None
        st.session_state._img_mime = None

    # 채팅 입력
    user_input = st.chat_input("대전 맛집을 물어보세요! 사진과 함께 질문해도 됩니다 🍽️")
    prompt = st.session_state.pending_prompt or user_input
    if st.session_state.pending_prompt:
        st.session_state.pending_prompt = None

    if prompt:
        img_bytes = st.session_state._img_bytes
        img_mime  = st.session_state._img_mime or "image/jpeg"
        has_image = bool(img_bytes) and model in VISION_MODELS

        if has_image:
            b64 = base64.b64encode(img_bytes).decode()
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{img_mime};base64,{b64}"}},
            ]
            st.session_state._img_bytes = None
            st.session_state._img_mime  = None
            st.session_state._img_key  += 1
        else:
            user_content = prompt

        st.session_state.messages.append({"role": "user", "content": user_content})
        with st.chat_message("user"):
            if has_image:
                st.markdown(prompt)
                st.image(img_bytes, width=280)
            else:
                st.markdown(prompt)

        trimmed = st.session_state.messages[-max_history:]
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m["role"], "content": m["content"]} for m in trimmed
        ]

        try:
            _raw_buf = []

            def _clean_stream(stream):
                """스트리밍하면서 PLACES_DATA JSON 블록을 실시간으로 필터링."""
                in_block = False
                tail = ""
                for chunk in stream:
                    delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                    _raw_buf.append(delta)
                    if in_block:
                        continue
                    combined = tail + delta
                    if "<!--PLACES_DATA" in combined:
                        in_block = True
                        idx = combined.index("<!--PLACES_DATA")
                        pre = combined[:idx].rstrip()
                        if pre:
                            yield pre
                        tail = ""
                    else:
                        safe = max(0, len(combined) - 25)
                        yield combined[:safe]
                        tail = combined[safe:]
                if tail and not in_block:
                    yield tail

            stream = client.chat.completions.create(
                model=model, messages=api_messages, stream=True
            )
            with st.chat_message("assistant"):
                st.write_stream(_clean_stream(stream))

            raw_full = "".join(_raw_buf)
            clean_text, places = parse_places(raw_full)

            st.session_state.messages.append({"role": "assistant", "content": clean_text})
            if places:
                st.session_state.last_places = places
                st.rerun()

        except AuthenticationError as e:
            st.error(f"API Key 오류: {e.message}", icon="🔑")
        except RateLimitError:
            st.error("요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.", icon="⏱️")
        except APIConnectionError as e:
            st.error(f"연결 오류: {e}", icon="🌐")
        except APIStatusError as e:
            st.error(f"API 오류 ({e.status_code}): {e.message}", icon="⚠️")
        except Exception as e:
            st.error(f"오류 ({type(e).__name__}): {e}", icon="⚠️")

# ──────────────────────────────────────────────────────────────────
with tab_mymap:
    if not st.session_state.my_places:
        st.info("채팅에서 **⭐ 저장** 버튼을 눌러 맛집을 저장해보세요!", icon="📍")
    else:
        st.markdown(f"**저장된 맛집 {len(st.session_state.my_places)}곳**")
        m2 = make_map(st.session_state.my_places, saved_names)
        st_folium(m2, width="100%", height=440, returned_objects=[])

        st.divider()
        for i, p in enumerate(st.session_state.my_places):
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.markdown(
                    f"**{i+1}. {p['name']}**  \n"
                    f"⭐ {p.get('rating_est','?')}/5 · {p.get('category','')} · 💰 {p.get('price_range','')}  \n"
                    f"📍 {p.get('address','')}"
                )
            with c2:
                st.link_button(
                    "지도", f"https://map.kakao.com/?q={p.get('address', p['name'])}",
                    use_container_width=True,
                )
            with c3:
                if st.button("삭제", key=f"del_mymap_{i}", use_container_width=True):
                    st.session_state.my_places.pop(i)
                    st.rerun()

        st.divider()
        if st.button("🗑️ 전체 삭제", use_container_width=True):
            st.session_state.my_places = []
            st.rerun()

# ──────────────────────────────────────────────────────────────────
with tab_plan:
    st.markdown("### 📅 AI 맛집 코스 계획")

    if not st.session_state.my_places:
        st.info("'나만의 지도' 탭에서 맛집을 저장하면 AI가 최적 방문 코스를 만들어드립니다!", icon="💡")
    else:
        st.markdown("**포함할 맛집 선택 (2곳 이상)**")
        selected_places = []
        for p in st.session_state.my_places:
            if st.checkbox(
                f"{p['name']} — {p.get('address','')} · {p.get('category','')}",
                key=f"plan_chk_{p['name']}",
            ):
                selected_places.append(p)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            outing_date = st.date_input("방문 날짜", value=datetime.now().date())
        with col_b:
            party_size = st.number_input("인원", 1, 20, 2)
        with col_c:
            start_time = st.time_input(
                "출발 시간",
                value=datetime.now().replace(hour=11, minute=0).time(),
            )

        extra = st.text_input(
            "추가 요청사항",
            placeholder="예: 주차 가능 위주, 카페 포함, 예산 2만원 이내...",
        )

        if st.button("🤖 AI 코스 만들기", type="primary", disabled=len(selected_places) < 2):
            place_desc = "\n".join(
                f"- {p['name']} ({p.get('category','')}, {p.get('address','')})"
                for p in selected_places
            )
            plan_prompt = (
                f"{outing_date.strftime('%Y년 %m월 %d일')} {start_time.strftime('%H:%M')} 출발, {party_size}명 기준.\n"
                f"아래 대전 맛집들을 최적 동선으로 방문하는 코스를 짜주세요.\n\n"
                f"{place_desc}\n\n"
                f"추가 요청: {extra or '없음'}\n\n"
                f"아래 형식으로 답변해주세요:\n"
                f"1. 방문 순서 및 이동 경로 (이유 포함)\n"
                f"2. 각 장소 도착 시각 및 예상 소요 시간\n"
                f"3. 이동 방법 (도보/차량/택시 거리 기준)\n"
                f"4. 총 예상 비용\n"
                f"5. 알아두면 좋은 팁"
            )
            with st.spinner("AI가 최적 코스를 계획 중..."):
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": plan_prompt},
                        ],
                    )
                    plan_text = resp.choices[0].message.content
                    clean_plan, _ = parse_places(plan_text)
                    st.session_state.plan_result = {
                        "text": clean_plan,
                        "places": selected_places,
                        "date": outing_date.strftime("%Y.%m.%d"),
                        "party": party_size,
                    }
                    st.rerun()
                except Exception as e:
                    st.error(f"오류: {e}")

        if st.session_state.plan_result:
            pr = st.session_state.plan_result
            st.divider()
            st.markdown(f"#### 📅 {pr['date']} 코스 — {pr['party']}명")
            st.markdown(pr["text"])

            with st.expander("🗺️ 코스 지도", expanded=True):
                m3 = make_map(pr["places"])
                st_folium(m3, width="100%", height=360, returned_objects=[])

            st.download_button(
                "💾 코스 저장 (TXT)",
                data=f"📅 {pr['date']} 대전 맛집 코스 ({pr['party']}명)\n\n{pr['text']}",
                file_name=f"daejeon_course_{pr['date'].replace('.','')}.txt",
                mime="text/plain",
            )
