"""API 请求模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Profile(BaseModel):
    sex: str = "男"
    age: int = 25
    height_cm: float = 170
    weight_kg: float = 60
    activity: str = "轻度"
    goal: str = "维持健康"


class MealPlanRequest(Profile):
    restrictions: Optional[list[str]] = None
    seed: Optional[int] = None


class DietItem(BaseModel):
    name: str
    grams: float = 100


class AnalyzeRequest(BaseModel):
    items: list[DietItem]
    sex: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity: Optional[str] = None
    goal: Optional[str] = None


class PlanRequest(Profile):
    restrictions: Optional[list[str]] = None
    city: str = "北京"
    keywords: Optional[str] = None
    budget: Optional[float] = None
    location: Optional[str] = None  # "lng,lat"


class WhereToEatRequest(BaseModel):
    city: str = "北京"
    keywords: Optional[str] = None
    budget: Optional[float] = None
    restrictions: Optional[list[str]] = None
    location: Optional[str] = None


class DashboardRequest(Profile):
    city: str = "北京"


class QueryRequest(BaseModel):
    question: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
