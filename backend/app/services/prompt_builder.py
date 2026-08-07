from app.schemas.story import StoryGenerationRequest

class PromptBuilder:
    def build_story_markdown(self, req: StoryGenerationRequest) -> str:
        """
        Builds clean, highly informative topic markdown without any meta tags like 'Scene 1' or 'Narrator'.
        """
        objectives_str = "\n".join([f"- {obj}" for obj in req.learning_objectives])
        custom_inst = f"\n\n## توجيهات خاصة:\n{req.custom_instructions}" if req.custom_instructions else ""
        
        md_content = f"""# {req.story_title}

## نظرة عامة والمفهوم الرئيسي
{req.story_idea}
{custom_inst}

## المحاور والترتيب التعليمي
{objectives_str}

## الشرح العلمي والتربوي التفصيلي

### 1. المفهوم والمقدمة الأساسية
شرح مباشر ومبسط لمفهوم {req.story_title} والتعريف المستهدف لمرحلة {req.education_level}.

### 2. الأسباب والعمليات والتأثير المباشر
تحليل علمي دقيق يعرض الأسباب والتفاعلات المرتبطة بـ {req.story_idea}.

### 3. جدول المقارنة والتفاصيل
عرض مقارنة شاملة تبين أوجه الاختلاف والتأثير المباشر بين المفاهيم المختلفة.

### 4. الخلاصة والتطبيق العملي
تقديم التوصيات والحلول العملية المباشرة للحفاظ على الصحة والمعرفة.
"""
        return md_content

    def build_notebooklm_prompt(self, req: StoryGenerationRequest = None) -> str:
        """
        Returns prompt for NotebookLM demanding direct scientific/topic slides without meta text.
        """
        user_inst = f"\nExtra User Instructions: {req.custom_instructions}" if req and req.custom_instructions else ""
        return f"""Create a highly detailed, professional educational presentation deck based on the uploaded source.

CRITICAL REQUIREMENTS:
- Language: Arabic (RTL)
- Direct Content: Get STRAIGHT to the topic matter! Do NOT include meta words like "Scene 1", "المشهد 1", "الراوي يقول", "الفصل الأول" in any slide title or body text.
- Design & Layout: Use rich visual elements, big slide numbers (like 1, 2, 3), comparison tables, blue callout cards, magnifying glass icons, doodles, and yellow marker highlights on key terms.
- Provide deep, accurate, detailed explanations for every slide.{user_inst}
- Generate the highest quality presentation possible!"""
