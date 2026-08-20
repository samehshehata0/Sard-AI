from app.schemas.story import StoryGenerationRequest
from app.core.config import settings


class PromptBuilder:
    def estimate_target_slide_count(self, req: StoryGenerationRequest) -> int:
        objectives = [item for item in req.learning_objectives if item.strip()]
        source_words = len(
            f"{req.story_title} {req.story_idea} {' '.join(objectives)}".split()
        )
        complexity_bonus = 2 if source_words >= 120 else 1 if source_words >= 55 else 0
        objective_bonus = min(4, max(0, len(objectives) - 1))
        return min(
            settings.MAX_SLIDES,
            max(settings.MIN_SLIDES, settings.TARGET_SLIDES + complexity_bonus + objective_bonus - 1),
        )

    def build_story_markdown(self, req: StoryGenerationRequest) -> str:
        """
        Builds clean, highly informative topic markdown without
        meta tags like 'Scene 1' or 'Narrator'.
        """

        objectives_str = "\n".join(
            [f"- {obj}" for obj in req.learning_objectives]
        )

        custom_inst = (
            f"\n\n## توجيهات خاصة:\n{req.custom_instructions}"
            if req.custom_instructions
            else ""
        )

        md_content = f"""# {req.story_title}

## نظرة عامة والمفهوم الرئيسي

{req.story_idea}
{custom_inst}

## المحاور والترتيب التعليمي

{objectives_str}

## الشرح العلمي والتربوي التفصيلي

### 1. المفهوم والمقدمة الأساسية

شرح مباشر ومبسط لمفهوم {req.story_title} والتعريف المستهدف
لمرحلة {req.education_level}.

### 2. الأسباب والعمليات والتأثير المباشر

تحليل علمي دقيق يعرض الأسباب والتفاعلات المرتبطة بـ
{req.story_idea}.

### 3. العلاقات والمقارنات

إذا كان الموضوع يحتوي على مفاهيم يمكن مقارنتها، يتم عرض مقارنة
واضحة توضح أوجه التشابه والاختلاف والعلاقات بينها.

إذا لم تكن المقارنة مناسبة لطبيعة الموضوع، يتم التركيز بدلًا منها
على العلاقات أو المراحل أو الأسباب والنتائج.

### 4. الأمثلة والتطبيقات

تقديم أمثلة واقعية ومبسطة تتناسب مع المرحلة التعليمية المستهدفة
وتساعد المتعلم على ربط المفهوم بالحياة اليومية.

### 5. الخلاصة والتطبيق العملي

تلخيص أهم الأفكار وربطها بالأهداف التعليمية والتطبيقات العملية
المناسبة للموضوع.
"""

        return md_content.strip()

    def build_notebooklm_prompt(
        self,
        req: StoryGenerationRequest = None,
        expansion_retry: bool = False,
    ) -> str:
        """
        Returns an optimized prompt for NotebookLM Video Overview
        generation in Arabic.
        """

        if req is None:
            return """
أنشئ Video Overview تعليميًا احترافيًا باللغة العربية اعتمادًا
حصريًا على المصدر المرفوع.

استخدم العربية الفصحى الطبيعية، واجعل الشرح واضحًا ومناسبًا
للفئة التعليمية المستهدفة.

ابدأ مباشرة بهوك تعليمي جذاب، ثم اشرح المفاهيم بتسلسل منطقي
مع الاعتماد على العناصر البصرية بدلًا من النصوص الطويلة.

لا تعرض أي مصطلحات إنتاجية مثل:
المشهد الأول، الراوي، Slide 1، Scene 1.

استخدم فقط المعلومات المدعومة بالمصدر ولا تخترع أي معلومات
أو أرقام أو دراسات.

أنشئ تجربة تعليمية بصرية متعددة الصفحات. لا تضغط الموضوع كله في
3 أو 4 شرائح. استخدم نحو 8 إلى 12 قسمًا بصريًا متميزًا عندما يحتوي
المصدر على مادة تعليمية كافية، واجعل لكل قسم فكرة تعليمية رئيسية واحدة.
""".strip()

        objectives_str = "\n".join(
            f"- {obj.strip()}"
            for obj in req.learning_objectives
            if obj.strip()
        )

        custom_instructions = (
            req.custom_instructions.strip()
            if req.custom_instructions
            else "No additional instructions."
        )

        learner_age = getattr(
            req,
            "student_age",
            "appropriate for the selected educational level"
        )

        learner_level = getattr(
            req,
            "student_level",
            "appropriate for the selected educational level"
        )

        educational_needs = getattr(
            req,
            "learning_needs",
            "clear explanation with suitable visual examples"
        )

        story_style = getattr(
            req,
            "story_style",
            "engaging educational"
        )

        voice_tone = getattr(
            req,
            "voice_tone",
            "clear and encouraging"
        )

        narrator_gender = getattr(
            req,
            "narrator_gender",
            "not specified"
        )

        retry_instruction = (
            f"\n\nThe previous result was too compressed. Expand it into at least "
            f"{settings.MIN_SLIDES} distinct visual sections. Do not compress the "
            "topic into only 3–4 slides, and do not duplicate sections."
            if expansion_retry
            else ""
        )

        return f"""
Create a high-quality educational Video Overview based strictly on the uploaded source.{retry_instruction}

## Context

Topic: {req.story_title}
Core idea: {req.story_idea}
Education level: {req.education_level}
Target age: {learner_age}
Prior knowledge: {learner_level}
Learner needs: {educational_needs}

Learning objectives:
{objectives_str}

Story style: {story_style}
Narration tone: {voice_tone}
Preferred narrator gender: {narrator_gender}

Additional instructions:
{custom_instructions}

## Output Language — Critical

ALL learner-facing output MUST be in clear, natural Modern Standard Arabic.

This includes:

- spoken narration
- titles
- labels
- captions
- questions
- summaries
- on-screen text

Do NOT output English to the learner.

Use correct Arabic RTL layout and age-appropriate Arabic vocabulary.

## Goal

Create an engaging Arabic educational VIDEO, not a text-heavy presentation.

The video must:

- accurately teach the topic
- cover all learning objectives
- match the learner's age and level
- use clear educational storytelling
- use meaningful visuals
- include natural Arabic narration
- progress logically from one idea to the next

## Structure

Use enough distinct visual sections to explain the topic properly.

Do NOT compress the topic into only 3–4 slides.

When the source provides enough content, aim for approximately 8–12 meaningful visual sections.

Use one main teaching idea per section.

Suggested flow:

Hook → Context → Core concept → Explanation → Example → Process/Cause & Effect → Application → Key Takeaways → Understanding Check

Adapt the flow to the topic; do not force irrelevant sections.

## Opening

Start directly with an engaging hook such as:

- a question
- a familiar real-life situation
- a simple problem
- a surprising observation

Avoid generic openings such as:

"في هذا الفيديو سنتعلم..."
"اليوم سنتحدث عن..."
"مرحبًا بكم..."

## Visuals

Think visually.

Prefer:

- diagrams
- illustrations
- arrows
- process flows
- timelines
- labeled visuals
- comparisons
- real-life examples
- highlighted keywords
- simple character interactions when appropriate

Visuals must explain the concept, not merely decorate the video.

Avoid long paragraphs on screen.

Narration should explain the details while visuals reinforce them.

## Story Style

Respect the selected style: {story_style}.

If dialogue-based:

- use short, natural Arabic dialogue
- keep dialogue educational
- avoid long speeches

If story-based:

- create a relatable situation
- introduce a question or challenge
- develop understanding through events
- end with a clear educational resolution

If explanatory:

- prioritize clarity
- use logical sequencing
- rely strongly on visual examples

## Narration

Use natural Arabic narration with tone: {voice_tone}.

The narration must:

- sound human and encouraging
- suit the learner's age
- use smooth transitions
- explain visuals instead of reading on-screen text word-for-word
- avoid unnecessary repetition

Apply narrator gender preference ({narrator_gender}) only if supported.

## Accuracy

Use ONLY information supported by the uploaded source.

Do NOT:

- invent facts
- invent statistics
- invent studies or references
- create unsupported claims
- add unnecessary advanced information

If information is uncertain or unsupported, omit it.

## Engagement

Use occasional short thinking prompts when useful, for example:

"برأيك، ماذا سيحدث؟"
"فكر للحظة..."
"لماذا تعتقد أن هذا يحدث؟"
"هل يمكنك اكتشاف الفرق؟"

Do not overuse them.

## Ending

End with:

1. a short recap
2. the most important learning points
3. a practical takeaway
4. optionally one short understanding question

Do not introduce new information at the end.

## Forbidden Output

Never show production/meta labels such as:

Scene 1
Slide 1
Narrator
Voiceover
Chapter 1
المشهد الأول
الشريحة الأولى
الراوي
الراوي يقول
تعليق صوتي
الفصل الأول

## Final Check

Before finalizing, verify:

- all learning objectives are covered
- all facts are source-grounded
- Arabic is natural and age-appropriate
- all visible and spoken learner-facing content is Arabic
- RTL is correct
- the topic is not compressed into too few visual sections
- each section has one clear educational purpose
- visuals support understanding
- there is no unnecessary repetition
- there are no long text-heavy screens
- the final result feels like a real educational video, not a PowerPoint deck

Produce the clearest, most accurate, engaging, and visually effective Arabic educational Video Overview possible.
""".strip()
