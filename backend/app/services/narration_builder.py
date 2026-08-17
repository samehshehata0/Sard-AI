import re
from typing import Iterable

from app.schemas.story import StoryGenerationRequest
from app.services.video_slide import VideoSlide


FORBIDDEN_META = re.compile(
    r"(?:NotebookLM|Slide\s*\d+|Scene\s*\d+|المشهد\s+(?:الأول|الثاني|الثالث|\d+)|"
    r"الشريحة\s+(?:الأولى|الثانية|الثالثة|\d+)|الراوي|تعليق\s+صوتي)",
    re.IGNORECASE,
)


def clean_learner_text(text: str) -> str:
    lines = []
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" -–—|\t")
        if not line or FORBIDDEN_META.search(line):
            continue
        if line.startswith(("http://", "https://", "file://")):
            continue
        lines.append(line)
    return "، ".join(lines)[:70]


class NarrationBuilder:
    def estimate_target_slide_count(self, req: StoryGenerationRequest) -> int:
        objectives = [item for item in req.learning_objectives if item.strip()]
        source_words = len(f"{req.story_title} {req.story_idea} {' '.join(objectives)}".split())
        complexity_bonus = 2 if source_words >= 120 else 1 if source_words >= 55 else 0
        objective_bonus = min(4, max(0, len(objectives) - 1))
        return min(16, max(8, 9 + complexity_bonus + objective_bonus))

    def _objective(self, objectives: list[str], index: int) -> str:
        if not objectives:
            return "فهم الفكرة الأساسية وربطها بالسلوك الصحيح"
        return objectives[index % len(objectives)].rstrip(".، ")

    def build(
        self,
        req: StoryGenerationRequest,
        visual_paths: list[str],
        slide_texts: Iterable[str] | None = None,
    ) -> list[VideoSlide]:
        if not visual_paths:
            raise ValueError("No slide visuals were provided")

        objectives = [item.strip() for item in req.learning_objectives if item.strip()]
        texts = list(slide_texts or [])
        roles = [
            "سؤال البداية",
            "الفكرة الأساسية",
            "المفهوم الأول",
            "مثال بصري",
            "العلاقة والنتيجة",
            "المفهوم التالي",
            "تطبيق من الحياة",
            "فكر وأجب",
            "ما الذي تعلمناه؟",
            "خطوة عملية",
            "مقارنة مفيدة",
            "خلاصة الرحلة",
        ]

        slides: list[VideoSlide] = []
        total = len(visual_paths)
        for index, visual_path in enumerate(visual_paths):
            page_text = clean_learner_text(texts[index] if index < len(texts) else "")
            objective = self._objective(objectives, max(0, index - 2))
            title = roles[index] if index < len(roles) else f"فكرة مهمة {index + 1}"

            if index == 0:
                narration = (
                    f"تخيل موقفًا نحتاج فيه إلى أن نقرر بسرعة: ما التصرف الأفضل تجاه {req.story_title}؟ "
                    f"سنبحث عن الإجابة من خلال {req.story_idea.rstrip('.، ')}، ثم نطبقها في حياتنا."
                )
            elif index == 1:
                narration = (
                    f"الفكرة التي تجمع رحلتنا هي {req.story_idea.rstrip('.، ')}. "
                    f"سنفهم معناها بلغة واضحة، ونربطها بهدف يمكن ملاحظته وتطبيقه."
                )
            elif index == total - 2:
                narration = (
                    f"توقف قليلًا وفكر: كيف تشرح بأسلوبك أن {objective}؟ "
                    f"اختر مثالًا من البيت أو المدرسة، وبيّن السلوك الصحيح ونتيجته."
                )
            elif index == total - 1:
                goals = "، و".join(item.rstrip(".، ") for item in objectives[:3]) or objective
                narration = (
                    f"نلخص رحلتنا في فكرة عملية: {goals}. "
                    f"يظهر الفهم عندما نلاحظ السبب والنتيجة، ثم نختار تصرفًا مسؤولًا ونشرحه للآخرين."
                )
            elif index % 4 == 2:
                narration = (
                    f"نركز هنا على هدف مهم: {objective}. "
                    f"ابحث في الصورة عن الفكرة الرئيسة، واربطها بموضوع {req.story_title}، ثم عبّر عنها بكلماتك."
                )
            elif index % 4 == 3:
                narration = (
                    f"لنحوّل الفكرة إلى مثال قريب. عندما نواجه موقفًا يتعلق بـ {req.story_title}، "
                    f"نلاحظ ما يحدث، ثم نسأل عن السبب ونتوقع النتيجة. هكذا يصبح {objective} فهمًا قابلًا للتطبيق."
                )
            elif index % 4 == 0:
                narration = (
                    f"توضح هذه الفكرة علاقة بين القرار والنتيجة. {objective}. "
                    f"فالاختيار الصغير يصنع أثرًا يتكرر، لذا نقارن بين السلوك الصحيح وتجاهله."
                )
            else:
                narration = (
                    f"الآن نربط ما تعلمناه بحياتنا اليومية. {objective}. "
                    f"نبدأ بخطوة بسيطة في البيت أو المدرسة، ثم نلاحظ أثرها ونشرح فائدتها."
                )

            if page_text and index not in {0, total - 1}:
                narration += f" وتوضح الصورة: {page_text}."

            narration = FORBIDDEN_META.sub("", narration)
            narration = re.sub(r"\s+", " ", narration).strip()
            slides.append(
                VideoSlide(
                    index=index + 1,
                    title=title,
                    visual_path=visual_path,
                    narration_text=narration,
                )
            )
        return slides
