from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


class UserRole(BaseModel):
    role: str
    organization_id: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str
    roles: List[UserRole] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    organization_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Organization(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    subscription_status: str = "trial"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Framework(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: str
    description: str
    version: str
    organization_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Control(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    framework_id: str
    control_id: str
    title: str
    description: str
    category: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Policy(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    title: str
    content: str
    version: str
    status: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ControlMapping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str = ""
    policy_id: str = ""
    policy_name: str = ""
    control_id: str = ""
    control_title: str = ""
    framework_id: str = ""
    framework_name: str = ""
    confidence_score: float = 0.0
    status: str = "approved"
    source: str = "manual"
    notes: str = ""
    ai_reason: str = ""
    mapped_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CrossFrameworkMapping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    source_control_id: str
    source_framework_id: str
    target_control_id: str
    target_framework_id: str
    mapping_strength: str
    notes: str = ""
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Quiz(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    training_id: str
    questions: List[Dict[str, Any]]
    passing_score: int = 70
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class QuizAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    quiz_id: str
    user_id: str
    answers: List[int]
    score: int
    passed: bool
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AuditEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str
    control_id: str
    evidence_type: str
    file_url: Optional[str] = None
    description: str
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Risk(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    title: str
    description: str
    category: str
    likelihood: int
    impact: int
    risk_score: int
    status: str
    owner: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Vendor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    name: str
    contact_email: str
    risk_level: str
    assessment_status: str
    last_assessment_date: Optional[datetime] = None
    next_assessment_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Audit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    title: str
    framework_ids: List[str]
    audit_type: str
    status: str
    scheduled_date: datetime
    completion_date: Optional[datetime] = None
    auditor: str
    findings: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Training(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    title: str
    description: str
    content: str
    duration_minutes: int
    required_for_roles: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TrainingCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    training_id: str
    user_id: str
    score: Optional[int] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str = ""
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[str] = None
    related_framework_id: Optional[str] = None
    related_control_id: Optional[str] = None
    tags: List[str] = []
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Request schemas used inline in routes
class FrameworkCreate(BaseModel):
    name: str
    description: str
    version: str

class PolicyCreate(BaseModel):
    title: str
    content: str
    version: str
    status: str

class RiskCreate(BaseModel):
    title: str
    description: str
    category: str
    likelihood: int
    impact: int
    status: str
    owner: str

class VendorCreate(BaseModel):
    name: str
    contact_email: str
    risk_level: str
    assessment_status: str

class AuditCreate(BaseModel):
    title: str
    framework_ids: List[str] = []
    audit_type: str
    status: str
    scheduled_date: str
    auditor: str

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    related_framework_id: Optional[str] = None
    related_control_id: Optional[str] = None
    tags: List[str] = []
