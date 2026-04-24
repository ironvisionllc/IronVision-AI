"""
Auto-Remediation Code Generation
- Generates fix code snippets (Terraform, CloudFormation, K8s YAML) for findings
- Maps vulnerability/compliance findings to infrastructure-as-code remediations
- Integrates with pipeline findings and Tenable POA&M entries
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import os
import re
import json
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/remediation", tags=["remediation"])

# ─── Remediation Templates ─────────────────────────────

REMEDIATION_TEMPLATES = {
    "encryption_at_rest": {
        "terraform": '''resource "aws_s3_bucket_server_side_encryption_configuration" "fix" {
  bucket = aws_s3_bucket.target.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
      kms_master_key_id = aws_kms_key.encryption_key.arn
    }
  }
}''',
        "cloudformation": '''Resources:
  S3BucketEncryption:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: aws:kms
              KMSMasterKeyID: !Ref EncryptionKey''',
        "kubernetes": '''apiVersion: v1
kind: Secret
metadata:
  name: encryption-config
  annotations:
    encryption: "AES-256"
type: Opaque
data:
  # Enable encryption at rest for etcd
  encryption-config.yaml: |
    kind: EncryptionConfiguration
    resources:
      - resources: ["secrets"]
        providers:
          - aescbc:
              keys:
                - name: key1
                  secret: <base64-encoded-key>''',
    },
    "mfa_enforcement": {
        "terraform": '''resource "aws_iam_policy" "mfa_required" {
  name   = "RequireMFA"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyAllExceptMFASetup"
      Effect    = "Deny"
      NotAction = ["iam:CreateVirtualMFADevice", "iam:EnableMFADevice",
                   "iam:GetUser", "iam:ListMFADevices",
                   "iam:ResyncMFADevice", "sts:GetSessionToken"]
      Resource  = "*"
      Condition = {
        BoolIfExists = { "aws:MultiFactorAuthPresent" = "false" }
      }
    }]
  })
}''',
        "cloudformation": '''Resources:
  MFAPolicy:
    Type: AWS::IAM::ManagedPolicy
    Properties:
      ManagedPolicyName: RequireMFA
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Sid: DenyWithoutMFA
            Effect: Deny
            NotAction: ["iam:CreateVirtualMFADevice", "iam:EnableMFADevice"]
            Resource: "*"
            Condition:
              BoolIfExists:
                aws:MultiFactorAuthPresent: false''',
    },
    "tls_enforcement": {
        "terraform": '''resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main.arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}''',
        "kubernetes": '''apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tls-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.2 TLSv1.3"
spec:
  tls:
    - hosts:
        - app.example.com
      secretName: tls-secret
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: app-service
                port:
                  number: 443''',
    },
    "firewall_restrict": {
        "terraform": '''resource "aws_security_group_rule" "deny_ssh_public" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["10.0.0.0/8"]  # Restrict to internal only
  security_group_id = aws_security_group.main.id
  description       = "SSH restricted to internal network only"
}''',
        "kubernetes": '''apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              purpose: internal
      ports:
        - protocol: TCP
          port: 443''',
    },
    "logging_enable": {
        "terraform": '''resource "aws_cloudtrail" "audit_trail" {
  name                       = "compliance-audit-trail"
  s3_bucket_name             = aws_s3_bucket.audit_logs.id
  include_global_service_events = true
  is_multi_region_trail      = true
  enable_log_file_validation = true
  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }
}''',
        "cloudformation": '''Resources:
  AuditTrail:
    Type: AWS::CloudTrail::Trail
    Properties:
      TrailName: compliance-audit-trail
      S3BucketName: !Ref AuditLogBucket
      IsMultiRegionTrail: true
      EnableLogFileValidation: true
      IncludeGlobalServiceEvents: true''',
    },
    "patch_management": {
        "terraform": '''resource "aws_ssm_patch_baseline" "production" {
  name             = "production-patch-baseline"
  operating_system = "AMAZON_LINUX_2"
  approval_rule {
    approve_after_days = 7
    compliance_level   = "CRITICAL"
    patch_filter {
      key    = "CLASSIFICATION"
      values = ["SecurityUpdates", "CriticalUpdates"]
    }
  }
}

resource "aws_ssm_maintenance_window" "patch_window" {
  name     = "weekly-patch-window"
  schedule = "cron(0 2 ? * SUN *)"
  duration = 3
  cutoff   = 1
}''',
    },
    "session_timeout": {
        "terraform": '''resource "aws_iam_policy" "session_timeout" {
  name   = "EnforceSessionTimeout"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = "*"
      Condition = {
        NumericLessThanEquals = {
          "aws:MaxSessionDuration" = "3600"
        }
      }
    }]
  })
}''',
        "kubernetes": '''apiVersion: v1
kind: ConfigMap
metadata:
  name: session-config
data:
  SESSION_TIMEOUT: "900"
  SESSION_IDLE_TIMEOUT: "600"
  ENFORCE_REAUTHENTICATION: "true"''',
    },
    "backup_config": {
        "terraform": '''resource "aws_backup_plan" "compliance" {
  name = "compliance-backup-plan"
  rule {
    rule_name         = "daily-backup"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 3 * * ? *)"
    lifecycle {
      delete_after = 90
    }
  }
}''',
    },
}

# Keyword → template mapping
FINDING_TO_TEMPLATE = {
    "encrypt": "encryption_at_rest",
    "kms": "encryption_at_rest",
    "s3.*encrypt": "encryption_at_rest",
    "mfa": "mfa_enforcement",
    "multi.factor": "mfa_enforcement",
    "tls": "tls_enforcement",
    "ssl": "tls_enforcement",
    "certificate": "tls_enforcement",
    "firewall": "firewall_restrict",
    "security.group": "firewall_restrict",
    "0.0.0.0": "firewall_restrict",
    "public.*access": "firewall_restrict",
    "ssh.*public": "firewall_restrict",
    "log": "logging_enable",
    "audit": "logging_enable",
    "cloudtrail": "logging_enable",
    "patch": "patch_management",
    "update": "patch_management",
    "vulnerab": "patch_management",
    "cve-": "patch_management",
    "session": "session_timeout",
    "timeout": "session_timeout",
    "inactiv": "session_timeout",
    "backup": "backup_config",
    "recover": "backup_config",
    "snapshot": "backup_config",
}


def match_template(title: str, description: str = "") -> str:
    """Match a finding to a remediation template via keywords."""
    text = f"{title} {description}".lower()
    for pattern, template_key in FINDING_TO_TEMPLATE.items():
        if re.search(pattern, text):
            return template_key
    return "patch_management"  # default


class RemediationRequest(BaseModel):
    finding_id: Optional[str] = None
    poam_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = "terraform"  # terraform, cloudformation, kubernetes


@router.post("/generate")
async def generate_remediation_code(req: RemediationRequest, current_user: Dict = Depends(get_current_user)):
    """Generate remediation code snippet for a finding or POA&M entry."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    title = req.title or ""
    description = req.description or ""

    # Resolve from finding or POA&M
    if req.finding_id:
        finding = await db.tenable_findings.find_one({"id": req.finding_id, "organization_id": org_id}, {"_id": 0})
        if not finding:
            finding = await db.pipeline_findings.find_one({"id": req.finding_id, "organization_id": org_id}, {"_id": 0})
        if finding:
            title = finding.get("title", title)
            description = finding.get("description", description)

    if req.poam_id:
        poam = await db.poam_entries.find_one({"id": req.poam_id, "organization_id": org_id}, {"_id": 0})
        if poam:
            title = poam.get("title", title)
            description = poam.get("description", description)

    if not title:
        raise HTTPException(400, "Provide a finding_id, poam_id, or title to generate remediation code")

    # Match template
    template_key = match_template(title, description)
    template = REMEDIATION_TEMPLATES.get(template_key, {})

    # Get code for requested format
    fmt = req.format or "terraform"
    code = template.get(fmt)

    # If no template match, use AI to generate
    if not code:
        code = await _ai_generate_remediation(title, description, fmt)

    # Also try to get AI-enhanced code
    ai_code = None
    try:
        ai_code = await _ai_generate_remediation(title, description, fmt)
    except Exception:
        pass

    # Store remediation
    remediation_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "finding_id": req.finding_id or "",
        "poam_id": req.poam_id or "",
        "title": title,
        "template_key": template_key,
        "format": fmt,
        "template_code": code or "",
        "ai_code": ai_code or "",
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.remediations.insert_one(remediation_doc)
    del remediation_doc["_id"]

    available_formats = list(template.keys()) if template else [fmt]

    return {
        "remediation": remediation_doc,
        "template_key": template_key,
        "available_formats": available_formats,
    }


async def _ai_generate_remediation(title: str, description: str, fmt: str) -> str:
    """Use GPT-5.2 to generate a remediation code snippet."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"remediation-{uuid.uuid4()}",
            system_message="You are an infrastructure security engineer. Generate precise, production-ready remediation code snippets."
        ).with_model("openai", "gpt-5.2")

        fmt_map = {"terraform": "Terraform HCL", "cloudformation": "AWS CloudFormation YAML", "kubernetes": "Kubernetes YAML manifest"}
        prompt = f"""Generate a {fmt_map.get(fmt, fmt)} code snippet to remediate this security finding:

Finding: {title}
Details: {description}

Requirements:
- Production-ready, copy-paste-able code
- Include comments explaining each section
- Follow security best practices
- Return ONLY the code block, no extra explanation"""

        response = await chat.send_message(UserMessage(text=prompt))
        text = response if isinstance(response, str) else str(response)
        # Extract code block if wrapped in markdown
        code_match = re.search(r'```(?:\w+)?\n([\s\S]*?)```', text)
        return code_match.group(1).strip() if code_match else text.strip()
    except Exception as e:
        logger.error(f"AI remediation generation failed: {e}")
        return ""


@router.get("/history")
async def list_remediations(current_user: Dict = Depends(get_current_user)):
    """List generated remediations."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    items = await db.remediations.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return items


@router.get("/templates")
async def list_templates():
    """List available remediation templates."""
    result = []
    for key, formats in REMEDIATION_TEMPLATES.items():
        result.append({"key": key, "name": key.replace("_", " ").title(), "formats": list(formats.keys())})
    return result
