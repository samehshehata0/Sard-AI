from typing import List, Optional
from pydantic import BaseModel, Field

class StoryGenerationRequest(BaseModel):
    story_id: Optional[str] = Field(None, description="معرف القصة من النواة")
    story_title: str = Field(..., description="العنوان الرئيسي للقصة")
    story_idea: str = Field(..., description="فكرة القصة الرواية والتفاصيل الكاملة")
    education_level: str = Field(..., description="المرحلة التعليمية للمتعلم")
    story_duration: str = Field(..., description="المدة الزمنية الكلية للقصة")
    learning_objectives: List[str] = Field(..., description="الأهداف التعليمية والتربوية")
    student_age: str = Field(..., description="عمر الفئة الموجه لها القصة")
    student_level: str = Field(..., description="مستوى الفهم القرائي والتعليمي")
    learning_needs: str = Field(..., description="الاحتياجات التربوية الخاصة")
    story_style: str = Field(..., description="أسلوب السرد والقصة")
    voice_tone: str = Field(..., description="نبرة التعليق الصوتي")
    narrator_gender: str = Field(..., description="جنس الراوي (male / female)")
    output_type: str = Field(..., description="نوع المخرجات (نص / صوت / فيديو)")
    custom_instructions: Optional[str] = Field(None, description="توجيهات وتفاصيل خاصة إضافية من المستخدم")

class StoryGenerationResponse(BaseModel):
    story_id: str
    status: str
    presentation_url: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: float
    created_at: str
    errors: Optional[List[str]] = None
