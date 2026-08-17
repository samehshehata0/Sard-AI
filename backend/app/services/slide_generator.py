import os
import logging
import hashlib
from typing import List
from app.schemas.story import StoryGenerationRequest

logger = logging.getLogger(__name__)

class SlideGenerator:
    def _get_theme(self, title: str):
        themes = [
            {"primary": "#0284c7", "bg": "#f8fafc", "border": "#bae6fd", "accent": "#fef08a"},
            {"primary": "#059669", "bg": "#f8fafc", "border": "#a7f3d0", "accent": "#fef08a"},
            {"primary": "#7c3aed", "bg": "#f8fafc", "border": "#ddd6fe", "accent": "#fef08a"},
            {"primary": "#ea580c", "bg": "#f8fafc", "border": "#fed7aa", "accent": "#fef08a"},
            {"primary": "#2563eb", "bg": "#f8fafc", "border": "#bfdbfe", "accent": "#fef08a"}
        ]
        idx = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16) % len(themes)
        return themes[idx]

    def generate_html_presentation(self, req: StoryGenerationRequest, output_path: str) -> str:
        """
        Generates a 100% flexible, multi-slide RTL Presentation Deck.
        Gives full design and content freedom per topic while completely eliminating meta text ("المشهد الأول").
        """
        title = req.story_title or "الدرس التعليمي"
        topic = req.story_idea or title
        objectives = [obj.strip() for obj in req.learning_objectives if obj.strip()]

        if not objectives:
            objectives = [
                f"نظرة عامة ومفاهيم أساسية حول {title}",
                f"الأسباب والتأثير المباشر لـ {topic}",
                "التطبيق والتفاعل الميداني",
                "الخلاصة والحلول العلمية"
            ]

        # This renderer is retained for direct/manual use only; the production
        # pipeline now requires NotebookLM visuals. Keep it pedagogically useful
        # and never let its historical objective-count formula collapse to 3–4 pages.
        expansion_sections = [
            f"سؤال يثير الفضول حول {title}",
            f"الفكرة الأساسية: {topic}",
            *objectives,
            f"الأسباب والنتائج المرتبطة بـ {title}",
            f"مثال من الحياة اليومية على {title}",
            f"تطبيق عملي يحقق الهدف التعليمي",
            f"سؤال قصير للتحقق من الفهم",
        ]
        unique_sections = []
        for section in expansion_sections:
            if section not in unique_sections:
                unique_sections.append(section)
        objectives = unique_sections[:14]

        theme = self._get_theme(title)
        total_slides = len(objectives) + 2

        slides_html = []

        # ==========================================
        # SLIDE 1: Title & Direct Topic Overview
        # ==========================================
        slides_html.append(f"""
    <!-- SLIDE 1: Cover -->
    <div class="slide">
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">{req.education_level}</div>
        </div>

        <div class="hero-container">
            <div class="hero-card">
                <div class="topic-badge">الموضوع الرئيسي</div>
                <h1 class="hero-title">{title}</h1>
                <p class="hero-description">{topic}</p>
            </div>
            <div class="big-number">1</div>
        </div>

        <div class="notebooklm-footer">
            <div class="notebooklm-logo"></div>
            <span>{title}</span>
        </div>
    </div>
""")

        # ==========================================
        # SLIDE 2..N: Dynamic Content Slides (Clean, No Meta Text)
        # ==========================================
        for idx, obj in enumerate(objectives):
            slide_num = idx + 2
            layout_type = idx % 4  # Rotate diverse layout structures freely

            if layout_type == 0:
                # Layout A: Split Highlight Card
                slide_content = f"""
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">المحور {idx + 1}</div>
        </div>

        <h2 class="section-title">{obj}</h2>

        <div class="split-card-row">
            <div class="content-card">
                <div class="card-icon">💡</div>
                <h3 class="card-heading">الشرح والتفسير العلمي</h3>
                <p class="card-text">تحليل مبسط ومباشر يوضح المفاهيم والمركبات الأساسية المرتبطة بـ ({obj}).</p>
                <div class="tag-highlight">توضيح مباشر</div>
            </div>

            <div class="content-card primary-card">
                <div class="card-icon">⚡</div>
                <h3 class="card-heading">الأثر والتفاعل</h3>
                <p class="card-text">ربط المفاهيم بالتطبيقات العملية والملاحظة المباشرة في البيئة المحيطة.</p>
                <div class="tag-highlight-yellow">تطبيق عملي</div>
            </div>
        </div>
"""
            elif layout_type == 1:
                # Layout B: 3-Step Process Flow
                slide_content = f"""
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">المحور {idx + 1}</div>
        </div>

        <h2 class="section-title">{obj}</h2>

        <div class="process-row">
            <div class="process-step">
                <div class="step-badge">01</div>
                <h3 class="step-heading">التساؤل والملاحظة</h3>
                <p class="step-text">استكشاف الظاهرة وطرح التساؤلات الرئيسية حول {title}.</p>
            </div>
            <div class="step-connector">➔</div>
            <div class="process-step">
                <div class="step-badge" style="background: {theme['primary']}; color: #fff;">02</div>
                <h3 class="step-heading">التجربة والتطبيق</h3>
                <p class="step-text">التفاعل المباشر وفهم العلاقات والأسباب.</p>
            </div>
            <div class="step-connector">➔</div>
            <div class="process-step">
                <div class="step-badge" style="background: #fef08a; color: #0f172a;">03</div>
                <h3 class="step-heading">النتيجة والترسيخ</h3>
                <p class="step-text">الوصول للفهم المكتمل وتحقيق الأهداف.</p>
            </div>
        </div>
"""
            elif layout_type == 2:
                # Layout C: Quad Grid Matrix
                slide_content = f"""
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">المحور {idx + 1}</div>
        </div>

        <h2 class="section-title">{obj}</h2>

        <div class="quad-grid">
            <div class="grid-item">
                <div class="item-icon">🔍</div>
                <h3 class="item-title">1. الفحص والملاحظة</h3>
                <p class="item-desc">ملاحظة التغيرات والعوامل المؤثرة.</p>
            </div>
            <div class="grid-item">
                <div class="item-icon">⚙️</div>
                <h3 class="item-title">2. التفاعل والعمليات</h3>
                <p class="item-desc">شرح خطوات ومراحل التغيير المباشر.</p>
            </div>
            <div class="grid-item">
                <div class="item-icon">📊</div>
                <h3 class="item-title">3. النتائج والأرقام</h3>
                <p class="item-desc">قياس التأثير ومقارنة المعطيات.</p>
            </div>
            <div class="grid-item">
                <div class="item-icon">🌟</div>
                <h3 class="item-title">4. التطبيق النهائي</h3>
                <p class="item-desc">الوصول إلى الاستنتاج العلمي السليم.</p>
            </div>
        </div>
"""
            else:
                # Layout D: Quote / Focus Callout Frame
                slide_content = f"""
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">المحور {idx + 1}</div>
        </div>

        <div class="callout-frame">
            <div class="frame-icon">💬</div>
            <p class="callout-text">
                عند دراسة <span class="highlight-yellow">{obj}</span>، نصل إلى فهم <span class="highlight-yellow">أشمل وأعمق</span> لآلية العمل وتأثيرها المباشر في <span class="highlight-yellow">{title}</span>.
            </p>
        </div>
"""

            slides_html.append(f"""
    <!-- SLIDE {slide_num} -->
    <div class="slide">
        {slide_content}
        <div class="notebooklm-footer">
            <div class="notebooklm-logo"></div>
            <span>{title}</span>
        </div>
    </div>
""")

        # ==========================================
        # FINAL SLIDE: Direct Summary & Key Takeaways
        # ==========================================
        slides_html.append(f"""
    <!-- FINAL SLIDE: Summary -->
    <div class="slide">
        <div class="slide-header">
            <div class="brand-tag">{title}</div>
            <div class="stage-tag">الخلاصة والتوصيات</div>
        </div>

        <div class="summary-card">
            <h2 class="summary-title">خلاصة وأبرز نتائج دراسة <span class="highlight-yellow">{title}</span></h2>
            <div class="summary-columns">
                <div class="summary-col">
                    <div class="summary-icon">🎯</div>
                    <h3>الفهم المباشر</h3>
                    <p>{objectives[0] if objectives else topic}</p>
                </div>
                <div class="summary-col">
                    <div class="summary-icon">🧠</div>
                    <h3>الاستنتاج العلمي</h3>
                    <p>ترسيخ المفاهيم المكتسبة وتطبيقها في الحياة العملية.</p>
                </div>
                <div class="summary-col">
                    <div class="summary-icon">🌟</div>
                    <h3>الأثر المستدام</h3>
                    <p>الحفاظ على المعرفة وتطوير مهارات الفهم والتحليل.</p>
                </div>
            </div>
        </div>

        <div class="notebooklm-footer">
            <div class="notebooklm-logo"></div>
            <span>{title}</span>
        </div>
    </div>
""")

        # Full CSS Styles with Clean Flexible Design
        full_html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1920, height=1080, initial-scale=1.0">
    <title>{title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@600;800;900&family=Tajawal:wght@700;900&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background-color: #f8fafc;
            color: #0f172a;
            font-family: 'Cairo', 'Tajawal', sans-serif;
            width: 1920px;
            height: 1080px;
            overflow: hidden;
        }}
        .slide {{
            width: 1920px;
            height: 1080px;
            position: relative;
            background-color: #f8fafc;
            background-size: 40px 40px;
            background-image: 
                linear-gradient(to right, rgba(203, 213, 225, 0.4) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(203, 213, 225, 0.4) 1px, transparent 1px);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 60px 90px;
            page-break-after: always;
        }}
        .slide-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px dashed #cbd5e1;
            padding-bottom: 20px;
        }}
        .brand-tag {{
            font-size: 28px;
            font-weight: 900;
            color: {theme['primary']};
        }}
        .stage-tag {{
            font-size: 22px;
            font-weight: 700;
            background: #e2e8f0;
            padding: 6px 22px;
            border-radius: 20px;
            color: #334155;
        }}
        .hero-container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: auto 0;
            gap: 40px;
        }}
        .hero-card {{
            flex: 1;
            background: #ffffff;
            border: 3px solid #cbd5e1;
            border-radius: 36px;
            padding: 60px 80px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.05);
            text-align: right;
        }}
        .topic-badge {{
            display: inline-block;
            background: #e0f2fe;
            color: #0369a1;
            font-size: 24px;
            font-weight: 800;
            padding: 6px 20px;
            border-radius: 16px;
            margin-bottom: 20px;
        }}
        .hero-title {{
            font-size: 68px;
            font-weight: 900;
            color: #0f172a;
            line-height: 1.3;
        }}
        .hero-description {{
            font-size: 32px;
            color: #475569;
            margin-top: 25px;
            line-height: 1.6;
            font-weight: 700;
        }}
        .big-number {{
            font-size: 260px;
            font-weight: 900;
            color: {theme['primary']};
            line-height: 1;
            padding-left: 40px;
        }}
        .section-title {{
            font-size: 44px;
            font-weight: 900;
            color: #0f172a;
            text-align: center;
            margin: 20px 0;
        }}
        .split-card-row {{
            display: flex;
            align-items: center;
            gap: 40px;
            margin: auto 0;
        }}
        .content-card {{
            flex: 1;
            height: 480px;
            background: #ffffff;
            border: 3px solid #cbd5e1;
            border-radius: 32px;
            padding: 40px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.04);
        }}
        .primary-card {{
            background: {theme['primary']};
            color: #ffffff;
            border-color: {theme['primary']};
        }}
        .primary-card .card-heading, .primary-card .card-text {{
            color: #ffffff;
        }}
        .card-icon {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        .card-heading {{
            font-size: 34px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 15px;
        }}
        .card-text {{
            font-size: 26px;
            color: #475569;
            line-height: 1.6;
            font-weight: 700;
        }}
        .tag-highlight {{
            margin-top: 25px;
            background: #e2e8f0;
            color: #334155;
            padding: 6px 20px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 22px;
        }}
        .tag-highlight-yellow {{
            margin-top: 25px;
            background: #fef08a;
            color: #0f172a;
            padding: 6px 20px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 22px;
        }}
        .process-row {{
            display: flex;
            align-items: center;
            gap: 30px;
            margin: auto 0;
        }}
        .process-step {{
            flex: 1;
            height: 460px;
            background: #ffffff;
            border: 3px solid #cbd5e1;
            border-radius: 28px;
            padding: 35px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
        }}
        .step-badge {{
            width: 70px;
            height: 70px;
            border-radius: 50%;
            background: #e2e8f0;
            color: #0f172a;
            font-size: 32px;
            font-weight: 900;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 20px;
        }}
        .step-heading {{
            font-size: 30px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 15px;
        }}
        .step-text {{
            font-size: 24px;
            color: #475569;
            line-height: 1.5;
            font-weight: 700;
        }}
        .step-connector {{
            font-size: 54px;
            color: #94a3b8;
            font-weight: 900;
        }}
        .quad-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin: auto 0;
        }}
        .grid-item {{
            background: #ffffff;
            border: 3px solid #cbd5e1;
            border-radius: 24px;
            padding: 35px;
            text-align: right;
        }}
        .item-icon {{
            font-size: 40px;
            margin-bottom: 12px;
        }}
        .item-title {{
            font-size: 28px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 10px;
        }}
        .item-desc {{
            font-size: 24px;
            color: #475569;
            font-weight: 700;
            line-height: 1.5;
        }}
        .callout-frame {{
            background: #ffffff;
            border: 4px solid {theme['primary']};
            border-radius: 36px;
            padding: 70px 90px;
            margin: auto 0;
            text-align: center;
            box-shadow: 0 15px 35px rgba(0,0,0,0.05);
        }}
        .frame-icon {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        .callout-text {{
            font-size: 46px;
            font-weight: 900;
            color: #0f172a;
            line-height: 1.7;
        }}
        .highlight-yellow {{
            background-color: #fef08a;
            color: #0f172a;
            padding: 4px 16px;
            border-radius: 10px;
            display: inline-block;
        }}
        .summary-card {{
            background: #ffffff;
            border: 3px solid #cbd5e1;
            border-radius: 36px;
            padding: 50px 70px;
            margin: auto 0;
            text-align: center;
        }}
        .summary-title {{
            font-size: 44px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 40px;
        }}
        .summary-columns {{
            display: flex;
            gap: 30px;
        }}
        .summary-col {{
            flex: 1;
            background: #f8fafc;
            border: 2px solid #e2e8f0;
            border-radius: 24px;
            padding: 30px;
            text-align: center;
        }}
        .summary-icon {{
            font-size: 48px;
            margin-bottom: 15px;
        }}
        .summary-col h3 {{
            font-size: 28px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 10px;
        }}
        .summary-col p {{
            font-size: 24px;
            color: #475569;
            font-weight: 700;
            line-height: 1.5;
        }}
        .notebooklm-footer {{
            position: absolute;
            bottom: 25px;
            left: 50px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
            font-weight: 800;
            color: #64748b;
        }}
        .notebooklm-logo {{
            width: 22px;
            height: 22px;
            background: radial-gradient(circle, #3b82f6 30%, #1d4ed8 70%);
            border-radius: 50%;
        }}
    </style>
</head>
<body>
{"".join(slides_html)}
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)
            
        logger.info(f"[SlideGenerator] Generated {total_slides} clean dynamic presentation slides -> {output_path}")
        return output_path
