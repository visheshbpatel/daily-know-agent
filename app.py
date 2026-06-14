
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.llm import provider_summary
from agent.lesson import generate_lesson
from agent.quiz import evaluate_answer, generate_quiz
from auth.auth_manager import OTP_SENT_MESSAGE, login_user, resend_otp, signup_user, verify_otp
from db.storage import (
    delete_session,
    get_history,
    get_quiz_attempts,
    get_user_by_username,
    init_db,
    save_quiz_result,
    save_session,
    verify_session_owner,
)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .card {padding: 1rem 1.2rem; border: 1px solid #2a2a2a; border-radius: 12px; margin-bottom: 0.8rem;}
        .auth-box {max-width: 420px; margin: 0 auto;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return ts


def _init_auth_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "current_user" not in st.session_state:
        st.session_state.current_user = None
    if "auth_view" not in st.session_state:
        st.session_state.auth_view = "login"
    if "pending_verification_email" not in st.session_state:
        st.session_state.pending_verification_email = None


def _reset_flow() -> None:
    for key in (
        "topic",
        "lesson",
        "session_id",
        "quiz_questions",
        "quiz_submitted",
        "quiz_score",
        "quiz_feedback",
        "topic_input",
        "selected_attempts",
    ):
        st.session_state.pop(key, None)
    for i in range(6):
        st.session_state.pop(f"quiz_q_{i}", None)
    st.session_state.step = "input"


def _logout() -> None:
    for key in (
        "authenticated",
        "current_user",
        "pending_verification_email",
        "verify_flow_username",
        "step",
        "topic",
        "lesson",
        "session_id",
        "quiz_questions",
        "quiz_submitted",
        "quiz_score",
        "quiz_feedback",
        "selected_attempts",
        "topic_input",
    ):
        st.session_state.pop(key, None)
    for i in range(6):
        st.session_state.pop(f"quiz_q_{i}", None)
    st.session_state.auth_view = "login"
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.rerun()


def _option_text_for_letter(q: dict, letter: str) -> str:
    let = (letter or "").strip().upper()[:1]
    for opt in q.get("options", []):
        o = str(opt).strip()
        if o.upper().startswith(let + ".") or o.upper().startswith(let + ")"):
            return opt
    for opt in q.get("options", []):
        if str(opt).strip().upper().startswith(let):
            return opt
    return let or "—"


def _ensure_state() -> None:
    if "step" not in st.session_state:
        st.session_state.step = "input"


def _open_history_item(row: dict) -> None:
    try:
        st.session_state.lesson = json.loads(row["lesson_text"])
    except json.JSONDecodeError:
        st.session_state.lesson = {"what_it_is": row["lesson_text"]}
    st.session_state.topic = row["topic"]
    st.session_state.session_id = row["id"]
    st.session_state.selected_attempts = get_quiz_attempts(int(row["id"]))
    st.session_state.step = "lesson"
    st.session_state.pop("quiz_questions", None)
    st.session_state.pop("quiz_submitted", None)
    st.session_state.pop("quiz_score", None)
    st.session_state.pop("quiz_feedback", None)
    st.rerun()


def show_login() -> None:
    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.title("Daily Knowledge Agent")
    st.markdown("*Type anything. Learn something. Prove it.*")
    st.subheader("Log in")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Login", type="primary", use_container_width=True):
            st.session_state.pop("verify_flow_username", None)
            if not str(username).strip() or not str(password).strip():
                st.warning("Enter username and password.")
            else:
                ok, payload = login_user(str(username).strip(), password)
                if ok and isinstance(payload, dict):
                    st.session_state.authenticated = True
                    st.session_state.current_user = payload
                    st.rerun()
                elif payload == "EMAIL_NOT_VERIFIED":
                    st.session_state.verify_flow_username = str(username).strip().lower()
                    st.warning("Your email is not verified yet.")
                else:
                    st.error("Invalid username or password.")
    with col_b:
        if st.button("Sign Up", use_container_width=True):
            st.session_state.auth_view = "signup"
            st.rerun()
    st.caption("Don't have an account? Tap **Sign Up**.")

    vu = st.session_state.get("verify_flow_username")
    if vu:
        row = get_user_by_username(vu)
        if row:
            if st.button("Verify my email", use_container_width=True):
                ok_r, msg_r = resend_otp(row["email"])
                if ok_r:
                    st.session_state.pending_verification_email = row["email"]
                    st.session_state.auth_view = "verify_otp"
                    st.session_state.pop("verify_flow_username", None)
                    st.rerun()
                else:
                    st.error(msg_r)
            if st.button("Dismiss", use_container_width=True):
                st.session_state.pop("verify_flow_username", None)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def show_signup() -> None:
    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.title("Create account")
    st.caption("Daily Knowledge Agent — private history per user.")
    username = st.text_input("Username", key="signup_username", help="3–20 characters: letters, numbers, underscores.")
    email = st.text_input("Email", key="signup_email")
    pw = st.text_input("Password", type="password", key="signup_pw")
    pw2 = st.text_input("Confirm password", type="password", key="signup_pw2")

    if st.button("Create Account", type="primary", use_container_width=True):
        if pw != pw2:
            st.error("Passwords do not match.")
            return
        ok, msg = signup_user(username, email, pw)
        if ok and msg == OTP_SENT_MESSAGE:
            st.session_state.pending_verification_email = str(email).strip().lower()
            st.session_state.auth_view = "verify_otp"
            st.rerun()
        elif ok:
            st.error("Unexpected signup response. Please try again.")
        else:
            st.error(msg)

    if st.button("Back to Login", use_container_width=True):
        st.session_state.auth_view = "login"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def show_verify_otp() -> None:
    email = st.session_state.pending_verification_email
    if not email:
        st.session_state.auth_view = "signup"
        st.rerun()
        return

    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.markdown("## Check your email")
    st.markdown(f"We sent a 6-digit code to **{email}**.")
    st.markdown("Enter it below to verify your account.")
    st.divider()

    otp_input = st.text_input(
        "Verification code",
        max_chars=6,
        placeholder="e.g. 482910",
        key="otp_input_field",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Verify", type="primary", use_container_width=True):
            code = str(otp_input).strip()
            if not code.isdigit() or len(code) != 6:
                st.error("Please enter a valid 6-digit code.")
            else:
                ok_v, msg_v = verify_otp(email, code)
                if ok_v:
                    st.success("Email verified. You can log in.")
                    st.session_state.auth_view = "login"
                    st.session_state.pending_verification_email = None
                    st.rerun()
                else:
                    st.error(msg_v)

    with col2:
        if st.button("Resend code", use_container_width=True):
            ok_r, msg_r = resend_otp(email)
            if ok_r:
                st.info("A new code has been sent to your email.")
            else:
                st.error(msg_r)

    st.divider()
    if st.button("Back to Sign Up", use_container_width=True):
        st.session_state.auth_view = "signup"
        st.session_state.pending_verification_email = None
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def show_auth_page() -> None:
    _inject_styles()
    if st.session_state.auth_view == "signup":
        show_signup()
    elif st.session_state.auth_view == "verify_otp":
        show_verify_otp()
    else:
        show_login()


def _render_sidebar() -> None:
    user = st.session_state.current_user or {}
    uid = int(user["id"])

    with st.sidebar:
        st.markdown(f"👤 **{user.get('username', '')}**")
        st.divider()

        step = st.session_state.get("step", "input")
        if step in ("lesson", "quiz"):
            if st.button("New topic", use_container_width=True, type="primary"):
                _reset_flow()
                st.rerun()
            st.divider()

        st.subheader("History")
        history = get_history(uid)
        if not history:
            st.info("No sessions yet. Learn something to build your history.")
        else:
            for row in history:
                attempts = int(row.get("attempts") or 0)
                best_score = row.get("score")
                score_note = f"best {best_score}/3" if best_score is not None else "quiz not taken"
                title = f"{row['topic'][:36]}{'…' if len(row['topic']) > 36 else ''}"
                with st.expander(f"{title}  |  {score_note}", expanded=False):
                    st.caption(f"Lesson date: {_fmt_ts(row.get('session_timestamp'))}")
                    st.caption(
                        f"Attempts: {attempts} | Last quiz: {_fmt_ts(row.get('last_quiz_timestamp'))}"
                    )
                    col_open, col_del = st.columns(2)
                    with col_open:
                        if st.button("Open", key=f"hist_open_{row['id']}", use_container_width=True):
                            _open_history_item(row)
                    with col_del:
                        if st.button("Delete", key=f"hist_del_{row['id']}", use_container_width=True):
                            deleted = delete_session(int(row["id"]), uid)
                            if deleted:
                                if st.session_state.get("session_id") == row["id"]:
                                    _reset_flow()
                                st.rerun()
                            else:
                                st.error("Could not delete.")

        st.divider()
        if st.button("Logout", use_container_width=True):
            _logout()


def _render_lesson(lesson: dict) -> None:
    st.subheader("Your lesson")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### What it is")
    st.write(lesson.get("what_it_is", ""))
    st.markdown("### Why it matters")
    st.write(lesson.get("why_it_matters", ""))
    st.markdown("### Key Facts")
    for fact in lesson.get("key_facts") or []:
        st.markdown(f"- {fact}")
    st.markdown("### Quick analogy")
    st.write(lesson.get("analogy", ""))
    st.markdown("### Real-world example")
    st.write(lesson.get("real_world_example", ""))
    st.markdown("</div>", unsafe_allow_html=True)

    code_block = lesson.get("code_snippet") or {}
    if isinstance(code_block, dict) and str(code_block.get("snippet") or "").strip():
        st.markdown("### Coding example")
        st.code(
            str(code_block.get("snippet", "")),
            language=str(code_block.get("language", "")).strip() or None,
        )
        if str(code_block.get("explanation") or "").strip():
            st.caption(str(code_block.get("explanation")))

    attempts = st.session_state.get("selected_attempts") or []
    if attempts:
        st.markdown("### Quiz attempt history")
        for idx, at in enumerate(attempts, start=1):
            header = f"Attempt {idx} — Score {at['score']} / 3 — {_fmt_ts(at.get('timestamp'))}"
            with st.expander(header, expanded=False):
                details = at.get("details") or []
                if not details:
                    st.caption("No per-question details stored for this older attempt.")
                else:
                    for q_idx, item in enumerate(details, start=1):
                        icon = "✅" if item.get("ok") else "❌"
                        st.markdown(f"{icon} **Q{q_idx}. {item.get('question', '')}**")
                        st.caption(f"Your answer: {item.get('user', '—')}")
                        st.caption(
                            f"Correct answer: {item.get('correct_text', item.get('correct', '—'))}"
                        )


def _render_quiz() -> None:
    questions = st.session_state.get("quiz_questions") or []
    submitted = st.session_state.get("quiz_submitted", False)

    if not questions:
        st.warning("No quiz loaded. Go back and open a lesson.")
        if st.button("Start over"):
            _reset_flow()
            st.rerun()
        return

    if not submitted:
        st.subheader("Quiz")
        for i, q in enumerate(questions):
            st.markdown(f"**{i + 1}. {q['question']}**")
            st.radio(
                "Choose an answer",
                options=q["options"],
                key=f"quiz_q_{i}",
                index=None,
                label_visibility="collapsed",
            )

        col_submit, col_retry = st.columns([1, 1])
        with col_submit:
            submit = st.button("Submit Quiz", type="primary", use_container_width=True)
        with col_retry:
            retry = st.button("Regenerate Quiz", use_container_width=True)

        if retry:
            lesson = st.session_state.get("lesson") or {}
            with st.spinner("Generating a fresh quiz..."):
                st.session_state.quiz_questions = generate_quiz(lesson)
                st.rerun()

        if submit:
            missing = any(st.session_state.get(f"quiz_q_{i}") is None for i in range(len(questions)))
            if missing:
                st.warning("Answer all three questions before submitting.")
                return

            score = 0
            feedback: list[dict] = []
            for i, q in enumerate(questions):
                user_ans = st.session_state[f"quiz_q_{i}"]
                correct = q["answer"]
                correct_text = _option_text_for_letter(q, str(correct))
                ok = evaluate_answer(q, user_ans, correct)
                if ok:
                    score += 1
                feedback.append(
                    {
                        "question": q["question"],
                        "user": user_ans,
                        "correct": correct,
                        "correct_text": correct_text,
                        "ok": ok,
                    }
                )
            sid = st.session_state.get("session_id")
            uid = (st.session_state.current_user or {}).get("id")
            if sid is not None and uid is not None:
                if verify_session_owner(int(sid), int(uid)):
                    save_quiz_result(int(sid), score, feedback)
                    st.session_state.selected_attempts = get_quiz_attempts(int(sid))
                else:
                    st.error("Could not save quiz results for this session.")
            st.session_state.quiz_submitted = True
            st.session_state.quiz_score = score
            st.session_state.quiz_feedback = feedback
            st.rerun()
    else:
        score = st.session_state.get("quiz_score", 0)
        st.success(f"You scored **{score} / 3**")
        feedback = st.session_state.get("quiz_feedback") or []
        questions = st.session_state.get("quiz_questions") or []
        for idx, row in enumerate(feedback):
            mark = "✅" if row["ok"] else "❌"
            st.markdown(f"{mark} **{row['question']}**")
            st.caption(f"Your answer: {row['user']}")
            q_ref = questions[idx] if idx < len(questions) else {}
            correct = _option_text_for_letter(q_ref, str(row["correct"]))
            st.caption(f"Correct ({row['correct']}): {correct}")

        col_back, col_quiz = st.columns([1, 1])
        with col_back:
            if st.button("Learn Something New", use_container_width=True):
                _reset_flow()
                st.rerun()
        with col_quiz:
            if st.button("Take Another Quiz", use_container_width=True):
                st.session_state.quiz_submitted = False
                st.session_state.pop("quiz_score", None)
                st.session_state.pop("quiz_feedback", None)
                lesson = st.session_state.get("lesson") or {}
                st.session_state.quiz_questions = generate_quiz(lesson)
                st.rerun()


def main() -> None:
    init_db()
    _init_auth_state()

    st.set_page_config(page_title="Daily Knowledge Agent", page_icon="📚", layout="wide")

    if not st.session_state.authenticated:
        show_auth_page()
        st.stop()

    _ensure_state()
    _inject_styles()
    st.title("Daily Knowledge Agent")
    st.markdown("*Type anything. Learn something. Prove it.*")
    _render_sidebar()

    step = st.session_state.step
    user = st.session_state.current_user or {}
    uid = int(user["id"])

    if step == "input":
        with st.container():
            topic = st.text_input(
                "What do you want to learn today?",
                key="topic_input",
                placeholder="e.g. photosynthesis, compound interest, Python decorators",
            )
            learn = st.button("Learn", type="primary")

        if learn:
            if not topic or not str(topic).strip():
                st.warning("Please enter a topic to continue.")
                return
            with st.spinner("Crafting your lesson..."):
                try:
                    lesson = generate_lesson(str(topic).strip())
                except Exception as exc:  # noqa: BLE001
                    st.error(
                        "We could not generate the lesson. Check `.env` provider keys and model.\n\n"
                        f"Details: {exc}"
                    )
                else:
                    session_id = save_session(
                        str(topic).strip(),
                        json.dumps(lesson, ensure_ascii=False),
                        uid,
                    )
                    st.session_state.topic = str(topic).strip()
                    st.session_state.lesson = lesson
                    st.session_state.session_id = session_id
                    st.session_state.selected_attempts = []
                    st.session_state.step = "lesson"
                    st.rerun()
    elif step == "lesson":
        st.caption(f"Topic: {st.session_state.get('topic', '')}")
        _render_lesson(st.session_state.get("lesson") or {})
        if st.button("Take the Quiz", type="primary"):
            with st.spinner("Preparing your quiz..."):
                try:
                    st.session_state.quiz_questions = generate_quiz(st.session_state.get("lesson") or {})
                    st.session_state.step = "quiz"
                    st.session_state.pop("quiz_submitted", None)
                    st.session_state.pop("quiz_score", None)
                    st.session_state.pop("quiz_feedback", None)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not generate the quiz.\n\nDetails: {exc}")
    elif step == "quiz":
        _render_quiz()


if __name__ == "__main__":
    main()