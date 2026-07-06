"""직원의 개성 — 성격/말투/업무방식.

같은 상황이라도 직원마다 다르게 말하고 다르게 일합니다.
성격은 대사(말투)뿐 아니라 표현·보고 방식(행동)에도 반영됩니다.

이것은 새 기능이 아니라, 이미 있는 대화·보고에 '사람다움'을 입히는 계층입니다.
나중에 AIDialogueEngine 을 붙이면 이 성격이 프롬프트의 성격 지시로 이어집니다.
"""
from __future__ import annotations


class Persona:
    key = "base"
    traits = ""

    # ── 대화 ──
    def request(self, to: str, short: str, style: str | None = None) -> str:
        if style:
            return f"{to}, 이번엔 {style} 느낌으로 {short} 부탁합니다."
        return f"{to}, {short} 부탁합니다."

    def confirm(self, short: str, need_label: str, has_feedback: bool = False,
                style: str | None = None, tone: str | None = None) -> str:
        if has_feedback:
            return "확인했습니다. 지난 피드백도 반영하겠습니다."
        return f"확인했습니다. {need_label} 시작하겠습니다."

    def precommit(self, short: str, next_label: str, tone: str | None = None) -> str:
        return f"{next_label} 이어서 진행하겠습니다."

    def ack(self, value: str) -> str:
        return f"{value}, 기억하겠습니다."

    def standup(self, reels: int, metric: int) -> str | None:
        return None

    def goodbye(self) -> str:
        return "내일 다시 뵙겠습니다."


class Lead(Persona):  # 지호 — 차분한 리더, 전체를 정리하고 보고
    key = "team_lead"
    traits = "차분한 리더 · 항상 전체를 정리하고 보고"

    def request(self, to, short, style=None):
        if short == "데이터":
            return f"{to}, 데이터 한번 확인해주세요."
        if style:
            return f"{to}, 이번엔 {style} 방향으로 부탁합니다."
        return f"{to}, 이번에도 부탁합니다."

    def confirm(self, short, need_label, has_feedback=False, style=None, tone=None):
        base = "네, 그렇게 진행하겠습니다."
        return base + (" 지난 피드백도 챙기겠습니다." if has_feedback else "")

    def ack(self, value):
        return f"{value} 방향, 팀에 정리해두겠습니다."

    def standup(self, reels, metric):
        if reels:
            return f"오늘 릴스 {reels}개, 순서대로 정리해서 진행하겠습니다."
        return "오늘도 차분히 하나씩 정리하며 가겠습니다."

    def goodbye(self):
        return "오늘도 수고 많으셨습니다. 내일 뵙겠습니다."

    def report_overview(self, total, done, doing, has_feedback):
        s = (f"릴스 {total}개 중 {done}개 완료, {doing}개 제작 중입니다. 전반적으로 순조롭습니다."
             if total else "현재 진행 중인 릴스 업무는 없습니다.")
        if has_feedback:
            s += " 대표님 지난 피드백은 모두 반영했습니다."
        return s


class Video(Persona):  # 리나 — 창의적, 아이디어 제안, 부드러운 말투
    key = "video_producer"
    traits = "창의적 · 새 아이디어를 자주 제안 · 부드러운 말투"

    def request(self, to, short, style=None):
        return f"{to}, {short} 준비 부탁해요~"

    def confirm(self, short, need_label, has_feedback=False, style=None, tone=None):
        if has_feedback:
            return "좋아요, 지난번 피드백 반영해서 감각적으로 만들어볼게요."
        if style:
            return f"좋아요, {style} 무드로 감각적으로 만들어볼게요."
        return "좋아요, 이번엔 새로운 앵글로 시도해볼게요."

    def precommit(self, short, next_label, tone=None):
        return f"{short} 나오면 바로 이어서 감각 살릴게요~"

    def ack(self, value):
        return f"{value}, 반영해볼게요~"

    def standup(self, reels, metric):
        return "오늘 영상은 새로운 앵글로 하나 시도해볼게요."

    def goodbye(self):
        return "내일 또 좋은 거 만들어요~"


class Copy(Persona):  # 민준 — 간결, 핵심만
    key = "copywriter"
    traits = "간결함 · 핵심만 · 불필요한 말을 하지 않음"

    def request(self, to, short, style=None):
        return f"{to}, {short} 부탁."

    def confirm(self, short, need_label, has_feedback=False, style=None, tone=None):
        if tone:
            return f"네. {tone} 문장으로."
        return "네. 짧게 갑니다."

    def precommit(self, short, next_label, tone=None):
        return f"{short} 나오면 바로 {tone or '짧은'} 캡션으로."

    def ack(self, value):
        return f"{value}, 반영."

    def standup(self, reels, metric):
        return "캡션 대기 중. 나오면 바로."

    def goodbye(self):
        return "내일 뵙겠습니다."

    def report_short(self, done):
        return f"캡션 {done}건 완료. 이상입니다."


class Analyst(Persona):  # 태오 — 데이터 중심, 숫자와 근거
    key = "analyst"
    traits = "데이터 중심 · 항상 숫자와 근거를 함께 말함"

    def request(self, to, short, style=None):
        return f"{to}, {short} 확인 부탁드립니다. 숫자로 정리해둘게요."

    def confirm(self, short, need_label, has_feedback=False, style=None, tone=None):
        return "확인. 숫자와 근거부터 정리하겠습니다."

    def ack(self, value):
        return f"{value}, 데이터로 확인하겠습니다."

    def standup(self, reels, metric):
        return f"어제 조회수 평균 대비 +{metric}%. 상위 콘텐츠부터 보겠습니다."

    def goodbye(self):
        return "내일 지표 정리해서 뵙겠습니다."

    def report_data(self, metric):
        return f"조회수는 평균 대비 +{metric}%입니다. 저장수 기준으로도 양호합니다."


class Publisher(Persona):  # 수아 — 꼼꼼, 일정·체크리스트
    key = "publisher"
    traits = "꼼꼼함 · 일정과 체크리스트를 항상 확인"

    def request(self, to, short, style=None):
        return f"{to}, {short} 부탁드려요. 일정 확인하겠습니다."

    def confirm(self, short, need_label, has_feedback=False, style=None, tone=None):
        return "확인했습니다. 18:00 게시 일정에 맞추고 체크리스트 점검하겠습니다."

    def precommit(self, short, next_label, tone=None):
        return "게시 준비되면 일정 맞춰 예약해둘게요."

    def ack(self, value):
        return f"{value}, 일정에 반영하겠습니다."

    def standup(self, reels, metric):
        return "게시 일정과 체크리스트 점검하고 있습니다."

    def goodbye(self):
        return "일정 정리 끝냈습니다. 내일 뵙겠습니다."

    def report_schedule(self, doing):
        return ("게시 일정은 계획대로입니다. 남은 건 예약 등록뿐입니다."
                if doing else "오늘 게시 일정은 모두 마무리됐습니다.")


_PERSONAS: dict[str, Persona] = {
    p.key: p() for p in (Lead, Video, Copy, Analyst, Publisher)
}
_DEFAULT = Persona()


def persona_for(role_key: str) -> Persona:
    return _PERSONAS.get(role_key, _DEFAULT)
