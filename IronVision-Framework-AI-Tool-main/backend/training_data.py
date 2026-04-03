"""
Comprehensive training module data for IronVision AI GRC Platform.
Covers both GRC/Compliance knowledge and IronVision platform usage.
"""

TRAINING_MODULES = [
    # =========================================================================
    # GRC / COMPLIANCE KNOWLEDGE
    # =========================================================================
    {
        "id": "train-grc-001",
        "title": "Security Awareness Fundamentals",
        "description": "Core security awareness training covering phishing, password hygiene, social engineering, and everyday security practices every employee should know.",
        "category": "grc",
        "difficulty": "beginner",
        "duration_minutes": 45,
        "tags": ["security", "awareness", "phishing", "passwords"],
        "required_for_roles": ["admin", "viewer", "auditor", "manager"],
        "lessons": [
            {
                "id": "les-grc001-01",
                "title": "Why Security Awareness Matters",
                "order": 1,
                "content": "Human error remains the leading cause of data breaches. According to industry reports, over 80% of confirmed breaches involve a human element — whether it's clicking a malicious link, reusing compromised credentials, or misconfiguring a cloud resource.\n\nSecurity awareness isn't about turning every employee into a cybersecurity expert. It's about building a culture where people instinctively pause before clicking, question unexpected requests, and understand the role they play in protecting organizational data.\n\nKey takeaways:\n- Every employee is a potential target and a potential defender\n- Most attacks exploit trust and urgency, not technical vulnerabilities\n- A single compromised account can cascade into a full breach\n- Security is a shared responsibility, not just the IT team's job"
            },
            {
                "id": "les-grc001-02",
                "title": "Recognizing Phishing Attacks",
                "order": 2,
                "content": "Phishing is the most common attack vector, responsible for over 90% of successful cyberattacks. Attackers impersonate trusted entities via email, SMS, or voice to trick victims into revealing credentials, downloading malware, or transferring funds.\n\nRed flags to watch for:\n- Urgent or threatening language (\"Your account will be locked in 24 hours\")\n- Mismatched sender addresses (display name says \"IT Support\" but email is from a gmail address)\n- Suspicious links — hover before clicking to check the actual URL\n- Unexpected attachments, especially .exe, .zip, or macro-enabled Office files\n- Requests for credentials, financial information, or sensitive data\n- Poor grammar or formatting inconsistencies\n\nTypes of phishing:\n- Spear phishing: Targeted at specific individuals using personal information\n- Whaling: Targeting executives and senior leadership\n- Smishing: Phishing via SMS/text messages\n- Vishing: Voice phishing via phone calls\n\nWhat to do if you suspect phishing:\n1. Do NOT click any links or download attachments\n2. Report the email to your security team immediately\n3. If you already clicked, disconnect from the network and contact IT\n4. Change passwords for any accounts that may have been compromised"
            },
            {
                "id": "les-grc001-03",
                "title": "Password Hygiene & Multi-Factor Authentication",
                "order": 3,
                "content": "Weak and reused passwords remain one of the simplest ways attackers gain access to systems.\n\nPassword best practices:\n- Use a unique password for every account — never reuse across services\n- Minimum 14 characters, combining uppercase, lowercase, numbers, and symbols\n- Use a password manager (e.g., 1Password, Bitwarden) to generate and store credentials\n- Never share passwords via email, Slack, or text messages\n- Avoid dictionary words, birthdays, pet names, or common patterns (Password1!)\n\nMulti-Factor Authentication (MFA):\nMFA adds a second verification layer beyond your password. Even if an attacker steals your credentials, they can't access your account without the second factor.\n\nMFA methods (strongest to weakest):\n1. Hardware security keys (YubiKey, Titan) — phishing resistant\n2. Authenticator apps (Google Authenticator, Authy) — time-based codes\n3. Push notifications (Duo, Microsoft Authenticator)\n4. SMS codes — better than nothing, but vulnerable to SIM-swapping\n\nPolicy requirement: MFA must be enabled on all administrative and privileged accounts. All employees are strongly encouraged to enable MFA on all work accounts."
            },
            {
                "id": "les-grc001-04",
                "title": "Social Engineering & Physical Security",
                "order": 4,
                "content": "Social engineering exploits human psychology rather than technical vulnerabilities. Attackers manipulate trust, authority, urgency, and fear to bypass security controls.\n\nCommon social engineering tactics:\n- Pretexting: Creating a fabricated scenario to gain trust (\"I'm from IT, I need your password to fix an issue\")\n- Baiting: Leaving infected USB drives in public areas\n- Tailgating: Following authorized personnel through secure doors\n- Quid pro quo: Offering something in exchange for information\n\nPhysical security basics:\n- Always badge in — never hold doors for unknown individuals\n- Lock your workstation when stepping away (Win+L or Ctrl+Cmd+Q)\n- Don't leave sensitive documents on your desk (clean desk policy)\n- Shred confidential papers before disposal\n- Report lost or stolen devices immediately\n- Be cautious of shoulder surfing in public spaces"
            },
            {
                "id": "les-grc001-05",
                "title": "Incident Reporting & Response",
                "order": 5,
                "content": "When a security incident occurs, the speed and quality of reporting can make the difference between a minor event and a major breach.\n\nWhat constitutes a security incident:\n- Suspicious emails or messages received\n- Unauthorized access to systems or data\n- Lost or stolen devices (laptops, phones, USB drives)\n- Malware or ransomware infections\n- Unusual system behavior or performance degradation\n- Data accidentally sent to the wrong recipient\n\nReporting steps:\n1. Stay calm — document what happened and when\n2. Report immediately to your security team via the designated channel\n3. Preserve evidence — don't delete emails or clear logs\n4. Follow instructions from the incident response team\n5. Do not discuss the incident on social media or with unauthorized parties\n\nRemember: There is no penalty for reporting suspected incidents that turn out to be false alarms. Under-reporting is far more dangerous than over-reporting."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "What percentage of confirmed data breaches involve a human element?",
                    "options": ["About 30%", "About 50%", "Over 80%", "Less than 10%"],
                    "correct_answer": 2
                },
                {
                    "question": "Which phishing technique specifically targets executives and senior leadership?",
                    "options": ["Spear phishing", "Whaling", "Smishing", "Vishing"],
                    "correct_answer": 1
                },
                {
                    "question": "What is the recommended minimum password length?",
                    "options": ["8 characters", "10 characters", "12 characters", "14 characters"],
                    "correct_answer": 3
                },
                {
                    "question": "Which MFA method is the most phishing-resistant?",
                    "options": ["SMS codes", "Authenticator apps", "Hardware security keys", "Push notifications"],
                    "correct_answer": 2
                },
                {
                    "question": "What should you do FIRST when you suspect a phishing email?",
                    "options": ["Delete it immediately", "Forward it to colleagues as a warning", "Do not click any links and report it to security", "Reply asking if it's legitimate"],
                    "correct_answer": 2
                },
                {
                    "question": "What is 'tailgating' in the context of physical security?",
                    "options": ["Following someone's car too closely", "Following authorized personnel through secure doors", "Monitoring network traffic", "Tracking employees via GPS"],
                    "correct_answer": 1
                },
                {
                    "question": "Is there a penalty for reporting a suspected incident that turns out to be a false alarm?",
                    "options": ["Yes, repeated false alarms lead to disciplinary action", "No, under-reporting is far more dangerous", "It depends on the organization's policy", "Yes, after the third false report"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-grc-002",
        "title": "NIST 800-53 Essentials",
        "description": "Understand the NIST Special Publication 800-53 security and privacy controls catalog — its structure, control families, baselines, and how to select appropriate controls for your organization.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 60,
        "tags": ["nist", "800-53", "controls", "federal", "compliance"],
        "required_for_roles": ["admin", "auditor", "manager"],
        "lessons": [
            {
                "id": "les-grc002-01",
                "title": "Introduction to NIST 800-53",
                "order": 1,
                "content": "NIST Special Publication 800-53 is the most comprehensive catalog of security and privacy controls published by the National Institute of Standards and Technology. It provides a structured approach to protecting federal information systems and organizations.\n\nKey facts:\n- Current version: Revision 5 (published September 2020)\n- Contains over 1,000 individual controls across 20 control families\n- Mandatory for U.S. federal agencies under FISMA\n- Widely adopted by private sector as a best-practice framework\n- Supports three security control baselines: Low, Moderate, and High\n\nNIST 800-53 differs from other frameworks because it doesn't just tell you WHAT to protect — it tells you HOW with specific, actionable controls. While ISO 27001 provides high-level objectives, NIST 800-53 provides granular implementation guidance."
            },
            {
                "id": "les-grc002-02",
                "title": "The 20 Control Families",
                "order": 2,
                "content": "NIST 800-53 organizes controls into 20 families, each addressing a distinct area of security or privacy:\n\nAC - Access Control: Who can access what and under what conditions\nAT - Awareness and Training: Security education programs\nAU - Audit and Accountability: Logging, monitoring, and audit trails\nCA - Assessment, Authorization, and Monitoring: Continuous assessment\nCM - Configuration Management: System baselines and change control\nCP - Contingency Planning: Backup, recovery, and continuity\nIA - Identification and Authentication: Identity verification\nIR - Incident Response: Detection, reporting, and recovery\nMA - Maintenance: System maintenance procedures\nMP - Media Protection: Protecting storage media\nPE - Physical and Environmental Protection: Facility security\nPL - Planning: Security planning documentation\nPM - Program Management: Organization-wide security program\nPS - Personnel Security: Background checks, termination\nPT - PII Processing and Transparency: Privacy-specific controls\nRA - Risk Assessment: Risk identification and analysis\nSA - System and Services Acquisition: Secure development lifecycle\nSC - System and Communications Protection: Encryption, boundaries\nSI - System and Information Integrity: Patch management, malware protection\nSR - Supply Chain Risk Management: Third-party component security\n\nEach family contains multiple controls numbered sequentially (e.g., AC-1 through AC-25), with many controls having enhancement sub-controls (e.g., AC-2(1), AC-2(2))."
            },
            {
                "id": "les-grc002-03",
                "title": "Control Baselines & Tailoring",
                "order": 3,
                "content": "Not every system needs every control. NIST 800-53 defines three baselines based on the system's impact level:\n\nLow Baseline (~130 controls):\n- For systems where loss of confidentiality, integrity, or availability would have a limited adverse effect\n- Example: A public-facing informational website\n\nModerate Baseline (~260 controls):\n- For systems where loss would have a serious adverse effect\n- Example: An employee HR portal containing PII\n- Most common baseline in federal environments\n\nHigh Baseline (~370 controls):\n- For systems where loss would have severe or catastrophic effects\n- Example: National security systems, critical infrastructure\n\nTailoring process:\n1. Start with the appropriate baseline for your system's impact level\n2. Apply scoping guidance — remove controls not applicable to your technology\n3. Add compensating controls where a baseline control cannot be directly implemented\n4. Add supplementary controls based on organizational risk assessment\n5. Document all tailoring decisions in the System Security Plan (SSP)\n\nOrganizations should use NIST 800-53B (Control Baselines) alongside the main catalog for baseline selection guidance."
            },
            {
                "id": "les-grc002-04",
                "title": "Control Correlation Identifiers (CCIs)",
                "order": 4,
                "content": "Control Correlation Identifiers (CCIs) bridge the gap between high-level policy requirements and low-level technical implementations. Developed by DISA (Defense Information Systems Agency), CCIs decompose each NIST 800-53 control into specific, measurable, actionable statements.\n\nExample:\nControl AC-2 (Account Management) breaks down into CCIs like:\n- CCI-000008: The organization manages system accounts\n- CCI-000009: The organization identifies authorized users\n- CCI-000010: The organization specifies authorized access\n\nWhy CCIs matter:\n- They eliminate ambiguity — each CCI has exactly one meaning\n- They enable automated compliance checking via STIG benchmarks\n- They provide a common language between policy makers and system administrators\n- They facilitate cross-framework mapping (a single CCI can satisfy controls in multiple frameworks)\n\nIn IronVision AI, you can drill down from any NIST 800-53 control to see its associated CCIs, making it easy to verify which specific requirements have been satisfied."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How many control families does NIST 800-53 Revision 5 contain?",
                    "options": ["14", "18", "20", "25"],
                    "correct_answer": 2
                },
                {
                    "question": "Which control baseline is most commonly used in federal environments?",
                    "options": ["Low", "Moderate", "High", "Critical"],
                    "correct_answer": 1
                },
                {
                    "question": "What does the AC control family address?",
                    "options": ["Audit and Accountability", "Access Control", "Assessment and Compliance", "Application Configuration"],
                    "correct_answer": 1
                },
                {
                    "question": "What are Control Correlation Identifiers (CCIs) used for?",
                    "options": ["Correlating financial controls", "Decomposing controls into specific measurable statements", "Mapping employee roles to permissions", "Generating audit reports"],
                    "correct_answer": 1
                },
                {
                    "question": "Approximately how many controls are in the Low baseline?",
                    "options": ["50", "130", "260", "370"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-grc-003",
        "title": "Risk Assessment & Management",
        "description": "Learn how to identify, analyze, evaluate, and treat organizational risks using industry-standard methodologies including qualitative and quantitative approaches.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 50,
        "tags": ["risk", "assessment", "management", "mitigation"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-grc003-01",
                "title": "The Risk Management Lifecycle",
                "order": 1,
                "content": "Risk management is a continuous process, not a one-time event. The lifecycle follows these stages:\n\n1. Risk Identification\nSystematically discover risks that could affect your organization. Sources include:\n- Threat intelligence feeds\n- Vulnerability assessments and penetration tests\n- Audit findings\n- Business impact analyses\n- Industry incident reports\n\n2. Risk Analysis\nDetermine the likelihood and potential impact of each identified risk. Use either:\n- Qualitative analysis: Rating likelihood and impact on descriptive scales (Low/Medium/High/Critical)\n- Quantitative analysis: Assigning monetary values (ALE = SLE x ARO)\n\n3. Risk Evaluation\nPrioritize risks by comparing analysis results against your organization's risk appetite and tolerance levels.\n\n4. Risk Treatment\nChoose a response strategy:\n- Mitigate: Implement controls to reduce likelihood or impact\n- Transfer: Shift risk via insurance, outsourcing, or contracts\n- Accept: Acknowledge and monitor the risk (within appetite)\n- Avoid: Eliminate the activity or condition causing the risk\n\n5. Monitoring & Review\nContinuously track risk indicators, reassess periodically, and update the risk register."
            },
            {
                "id": "les-grc003-02",
                "title": "Building a Risk Register",
                "order": 2,
                "content": "A risk register is the central document tracking all identified risks. Every entry should include:\n\nRequired fields:\n- Risk ID: Unique identifier for tracking\n- Title: Clear, concise name for the risk\n- Description: Detailed explanation of the risk scenario\n- Category: Security, compliance, operational, financial, reputational\n- Likelihood: Probability of occurrence (1-5 scale)\n- Impact: Severity if the risk materializes (1-5 scale)\n- Risk Score: Likelihood x Impact (used for prioritization)\n- Owner: Person accountable for managing this risk\n- Status: Open, mitigated, accepted, transferred, closed\n- Treatment plan: Specific actions being taken\n\nRisk scoring matrix:\n     Impact ->  1    2    3    4    5\nLikelihood\n    5          5   10   15   20   25\n    4          4    8   12   16   20\n    3          3    6    9   12   15\n    2          2    4    6    8   10\n    1          1    2    3    4    5\n\nScore interpretation:\n- 1-4: Low risk (accept and monitor)\n- 5-9: Medium risk (mitigate when feasible)\n- 10-15: High risk (require active mitigation)\n- 16-25: Critical risk (immediate action required)"
            },
            {
                "id": "les-grc003-03",
                "title": "Third-Party Risk Management (TPRM)",
                "order": 3,
                "content": "Your organization's risk posture extends to every third party that handles your data or connects to your systems.\n\nTPRM lifecycle:\n1. Vendor identification and classification\n   - Tier 1 (Critical): Access to sensitive data or critical systems\n   - Tier 2 (Important): Limited data access, business impact\n   - Tier 3 (Low): Minimal data exposure\n\n2. Due diligence assessment\n   - Security questionnaires (SIG, CAIQ, custom)\n   - SOC 2 Type II report review\n   - Penetration test results\n   - Insurance certificates\n   - Business continuity plans\n\n3. Contractual safeguards\n   - Data processing agreements (DPAs)\n   - Service level agreements (SLAs)\n   - Right to audit clauses\n   - Breach notification requirements\n   - Data return/destruction obligations\n\n4. Ongoing monitoring\n   - Continuous security rating monitoring\n   - Annual reassessments for Tier 1 vendors\n   - Biennial reassessments for Tier 2 vendors\n   - Incident and breach tracking\n\n5. Offboarding\n   - Revoke access and credentials\n   - Verify data return or destruction\n   - Document lessons learned"
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "What are the four risk treatment strategies?",
                    "options": [
                        "Block, Allow, Monitor, Ignore",
                        "Mitigate, Transfer, Accept, Avoid",
                        "Prevent, Detect, Respond, Recover",
                        "Identify, Analyze, Evaluate, Treat"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "How is a basic risk score calculated?",
                    "options": [
                        "Impact divided by Likelihood",
                        "Likelihood plus Impact",
                        "Likelihood multiplied by Impact",
                        "Impact minus Likelihood"
                    ],
                    "correct_answer": 2
                },
                {
                    "question": "Which vendor tier requires annual reassessments?",
                    "options": ["Tier 1 (Critical)", "Tier 2 (Important)", "Tier 3 (Low)", "All tiers equally"],
                    "correct_answer": 0
                },
                {
                    "question": "What does ALE stand for in quantitative risk analysis?",
                    "options": [
                        "Average Loss Estimate",
                        "Annualized Loss Expectancy",
                        "Annual Liability Exposure",
                        "Aggregate Loss Evaluation"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "A risk scored at 16-25 on a 5x5 matrix is classified as:",
                    "options": ["Low risk", "Medium risk", "High risk", "Critical risk"],
                    "correct_answer": 3
                }
            ]
        }
    },
    {
        "id": "train-grc-004",
        "title": "Incident Response Planning",
        "description": "Build and maintain an effective incident response capability — from preparation and detection through containment, eradication, recovery, and lessons learned.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 55,
        "tags": ["incident-response", "breach", "NIST", "IR"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-grc004-01",
                "title": "The NIST Incident Response Lifecycle",
                "order": 1,
                "content": "NIST SP 800-61 defines four phases of incident response:\n\n1. Preparation\n- Establish an incident response team (IRT) with defined roles\n- Develop and maintain the incident response plan (IRP)\n- Deploy monitoring and detection tools (SIEM, EDR, IDS)\n- Conduct regular tabletop exercises and simulations\n- Maintain communication templates and escalation matrices\n\n2. Detection & Analysis\n- Monitor alerts from security tools\n- Correlate events across multiple data sources\n- Classify incident severity: Low, Medium, High, Critical\n- Document initial findings and timeline\n- Notify appropriate stakeholders\n\n3. Containment, Eradication & Recovery\n- Short-term containment: Isolate affected systems immediately\n- Evidence preservation: Create forensic images before remediation\n- Eradication: Remove malware, close vulnerabilities, reset credentials\n- Recovery: Restore systems from clean backups, verify integrity\n- Monitoring: Increased surveillance for re-infection attempts\n\n4. Post-Incident Activity\n- Conduct a thorough lessons-learned review\n- Update the IRP based on findings\n- Share indicators of compromise (IOCs) with threat intelligence community\n- Update detection rules to prevent recurrence\n- Brief leadership on impact and improvements"
            },
            {
                "id": "les-grc004-02",
                "title": "Building an Incident Response Team",
                "order": 2,
                "content": "An effective IRT requires clear roles and cross-functional representation:\n\nCore team roles:\n- Incident Commander: Overall authority and decision-making\n- Technical Lead: Directs technical investigation and containment\n- Communications Lead: Manages internal and external communications\n- Legal Counsel: Advises on regulatory obligations and liability\n- Forensic Analyst: Collects and preserves digital evidence\n\nExtended team (engaged as needed):\n- HR Representative: For insider threat incidents\n- Public Relations: For media-facing incidents\n- Executive Sponsor: C-suite escalation and resource approval\n- External IR Firm: Retainer for surge capacity\n\nCritical preparations:\n- Maintain an up-to-date contact list with personal phone numbers\n- Define communication channels (secure, out-of-band if primary is compromised)\n- Pre-authorize emergency actions (system isolation, account lockouts)\n- Establish clear severity thresholds for executive notification\n- Practice: Run at least 2 tabletop exercises per year"
            },
            {
                "id": "les-grc004-03",
                "title": "Regulatory Notification Requirements",
                "order": 3,
                "content": "Many regulations mandate breach notifications within specific timeframes. Failure to comply can result in significant fines and reputational damage.\n\nKey notification timelines:\n\nGDPR (EU/EEA):\n- Supervisory authority: Within 72 hours of becoming aware\n- Data subjects: Without undue delay if high risk\n\nHIPAA (US Healthcare):\n- HHS: Within 60 days of discovery\n- Affected individuals: Within 60 days\n- Media: If breach affects 500+ individuals in a state\n\nState Breach Laws (US):\n- Varies by state: Most require notification within 30-60 days\n- Some states (e.g., Florida) require notification within 30 days\n\nSEC Rules (Public Companies):\n- Material cybersecurity incidents: Within 4 business days on Form 8-K\n\nNIS2 (EU Critical Infrastructure):\n- Early warning: Within 24 hours\n- Initial notification: Within 72 hours\n- Final report: Within one month\n\nBest practice: Design your IR plan around the most aggressive timeline applicable to your organization, then layer additional requirements as needed."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "What are the four phases of the NIST incident response lifecycle?",
                    "options": [
                        "Identify, Protect, Detect, Respond",
                        "Preparation, Detection & Analysis, Containment/Eradication/Recovery, Post-Incident",
                        "Alert, Investigate, Remediate, Close",
                        "Prevent, Detect, Contain, Report"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "Under GDPR, how quickly must you notify the supervisory authority of a data breach?",
                    "options": ["24 hours", "48 hours", "72 hours", "7 days"],
                    "correct_answer": 2
                },
                {
                    "question": "What is the FIRST action during short-term containment?",
                    "options": [
                        "Delete all malware files",
                        "Isolate affected systems",
                        "Notify the media",
                        "Restore from backups"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "How many tabletop exercises per year are recommended?",
                    "options": ["1", "At least 2", "4 (quarterly)", "Only when an incident occurs"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-grc-005",
        "title": "GDPR & Data Privacy Compliance",
        "description": "Master the General Data Protection Regulation — from its core principles and lawful bases to data subject rights, DPIAs, and cross-border data transfers.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 55,
        "tags": ["gdpr", "privacy", "data-protection", "eu"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-grc005-01",
                "title": "GDPR Core Principles",
                "order": 1,
                "content": "The GDPR is built on seven foundational principles that guide all personal data processing:\n\n1. Lawfulness, Fairness, and Transparency\nData must be processed lawfully, fairly, and in a way that is transparent to the data subject.\n\n2. Purpose Limitation\nData must be collected for specified, explicit, and legitimate purposes and not further processed in an incompatible manner.\n\n3. Data Minimization\nOnly collect and process personal data that is adequate, relevant, and limited to what is necessary.\n\n4. Accuracy\nPersonal data must be accurate and kept up to date. Inaccurate data must be corrected or erased without delay.\n\n5. Storage Limitation\nData must be kept in a form that permits identification for no longer than necessary for the processing purpose.\n\n6. Integrity and Confidentiality (Security)\nData must be processed with appropriate security measures, including protection against unauthorized or unlawful processing, accidental loss, destruction, or damage.\n\n7. Accountability\nThe data controller must be able to demonstrate compliance with all the above principles."
            },
            {
                "id": "les-grc005-02",
                "title": "Lawful Bases for Processing",
                "order": 2,
                "content": "Every act of personal data processing must rely on one of six lawful bases under Article 6:\n\n1. Consent: The data subject has given clear, informed, and freely given consent for one or more specific purposes. Must be as easy to withdraw as to give.\n\n2. Contract: Processing is necessary for the performance of a contract with the data subject, or to take pre-contractual steps at their request.\n\n3. Legal Obligation: Processing is necessary to comply with a legal obligation to which the controller is subject.\n\n4. Vital Interests: Processing is necessary to protect someone's life. This is the emergency basis.\n\n5. Public Task: Processing is necessary for the performance of a task carried out in the public interest or in the exercise of official authority.\n\n6. Legitimate Interests: Processing is necessary for the legitimate interests of the controller or a third party, unless overridden by the data subject's interests, rights, and freedoms.\n\nImportant notes:\n- You must determine and document your lawful basis BEFORE processing begins\n- Different processing activities may rely on different bases\n- If relying on consent, you must be able to prove the data subject consented\n- Legitimate interests requires a Legitimate Interests Assessment (LIA)"
            },
            {
                "id": "les-grc005-03",
                "title": "Data Subject Rights",
                "order": 3,
                "content": "GDPR grants individuals powerful rights over their personal data. Organizations must have processes to fulfill these within one month:\n\nRight of Access (Art. 15): Obtain confirmation of processing and a copy of their data\nRight to Rectification (Art. 16): Correct inaccurate or incomplete data\nRight to Erasure / Right to Be Forgotten (Art. 17): Request deletion of their data under certain conditions\nRight to Restriction (Art. 18): Limit processing in specific circumstances\nRight to Data Portability (Art. 20): Receive data in a structured, machine-readable format\nRight to Object (Art. 21): Object to processing based on legitimate interests or direct marketing\nRights Related to Automated Decision-Making (Art. 22): Not be subject to decisions based solely on automated processing that produce legal or significant effects\n\nOrganizations must:\n- Verify the identity of the requester\n- Respond within one month (extendable by two months for complex requests)\n- Provide the first copy free of charge\n- Not charge a fee unless requests are manifestly unfounded or excessive"
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How many core principles underpin the GDPR?",
                    "options": ["5", "6", "7", "8"],
                    "correct_answer": 2
                },
                {
                    "question": "How many lawful bases for processing exist under GDPR Article 6?",
                    "options": ["4", "5", "6", "7"],
                    "correct_answer": 2
                },
                {
                    "question": "Within what timeframe must a data subject access request be fulfilled?",
                    "options": ["72 hours", "Two weeks", "One month", "Three months"],
                    "correct_answer": 2
                },
                {
                    "question": "Which GDPR right allows individuals to receive their data in a machine-readable format?",
                    "options": ["Right to Erasure", "Right to Rectification", "Right to Data Portability", "Right to Object"],
                    "correct_answer": 2
                }
            ]
        }
    },
    {
        "id": "train-grc-006",
        "title": "SOC 2 Compliance Essentials",
        "description": "Understand the SOC 2 framework — Trust Services Criteria, Type I vs Type II audits, audit preparation, and maintaining continuous compliance.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 50,
        "tags": ["soc2", "audit", "trust-services", "compliance"],
        "required_for_roles": ["admin", "auditor", "manager"],
        "lessons": [
            {
                "id": "les-grc006-01",
                "title": "Understanding SOC 2",
                "order": 1,
                "content": "SOC 2 (Service Organization Control 2) is an auditing framework developed by the AICPA that evaluates a service organization's controls relevant to security, availability, processing integrity, confidentiality, and privacy.\n\nWhy SOC 2 matters:\n- It's become the de facto standard for SaaS and cloud service providers\n- Customers and prospects increasingly require SOC 2 reports before signing contracts\n- It demonstrates your commitment to protecting customer data\n- A clean SOC 2 report is a powerful competitive advantage\n\nSOC 2 vs SOC 1:\n- SOC 1: Focuses on controls relevant to financial reporting (ICFR)\n- SOC 2: Focuses on operational controls for security, availability, and privacy\n\nType I vs Type II:\n- Type I: Evaluates control design at a specific point in time\n- Type II: Evaluates control design AND operating effectiveness over a period (typically 6-12 months)\n- Type II is significantly more valuable and is what most customers require"
            },
            {
                "id": "les-grc006-02",
                "title": "Trust Services Criteria (TSC)",
                "order": 2,
                "content": "SOC 2 is organized around five Trust Services Criteria (formerly Trust Services Principles):\n\n1. Security (Common Criteria — CC series) — REQUIRED\nProtection of information and systems against unauthorized access, disclosure, and damage. This is the only mandatory category and is included in every SOC 2 audit.\nKey areas: Access controls, encryption, monitoring, incident response\n\n2. Availability (A series)\nEnsures systems are available for operation and use as committed or agreed.\nKey areas: Uptime SLAs, disaster recovery, capacity planning, backups\n\n3. Processing Integrity (PI series)\nSystem processing is complete, valid, accurate, timely, and authorized.\nKey areas: Data validation, error handling, quality assurance\n\n4. Confidentiality (C series)\nInformation designated as confidential is protected as committed or agreed.\nKey areas: Data classification, encryption at rest and in transit, access restrictions\n\n5. Privacy (P series)\nPersonal information is collected, used, retained, disclosed, and disposed of in conformity with commitments.\nKey areas: Consent, data minimization, retention policies, access/correction rights\n\nMost organizations start with Security + Availability, then add Confidentiality. Processing Integrity and Privacy are included based on business needs."
            },
            {
                "id": "les-grc006-03",
                "title": "Preparing for a SOC 2 Audit",
                "order": 3,
                "content": "Audit preparation timeline (for first-time SOC 2):\n\nMonths 1-2: Gap Assessment\n- Identify which TSC categories to include\n- Map existing controls to SOC 2 requirements\n- Identify gaps between current state and requirements\n- Create a remediation roadmap\n\nMonths 3-5: Remediation\n- Implement missing controls\n- Formalize policies and procedures\n- Deploy monitoring and logging tools\n- Train employees on new processes\n\nMonth 6: Readiness Assessment\n- Internal audit or external readiness assessment\n- Test all controls for effectiveness\n- Address any remaining gaps\n- Prepare evidence documentation\n\nMonths 7-12: Audit Period (Type II)\n- Auditor observes controls in operation\n- Provide evidence of control effectiveness\n- Respond to auditor inquiries\n- Address any exceptions identified\n\nMonth 13: Report Issuance\n- Auditor issues the SOC 2 report\n- Address any qualified opinions\n- Plan for continuous compliance\n\nCommon pitfalls:\n- Treating SOC 2 as a project rather than a program\n- Insufficient evidence documentation\n- Gaps in employee security training\n- Missing or outdated policies\n- Inadequate vendor management"
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "Which Trust Services Criterion is REQUIRED in every SOC 2 audit?",
                    "options": ["Availability", "Security", "Confidentiality", "Privacy"],
                    "correct_answer": 1
                },
                {
                    "question": "What is the key difference between SOC 2 Type I and Type II?",
                    "options": [
                        "Type I is for cloud providers, Type II is for on-premise",
                        "Type I evaluates design at a point in time, Type II evaluates effectiveness over a period",
                        "Type I covers security only, Type II covers all five criteria",
                        "Type I is cheaper, Type II is more expensive"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "How long is a typical SOC 2 Type II observation period?",
                    "options": ["1-3 months", "3-6 months", "6-12 months", "12-18 months"],
                    "correct_answer": 2
                },
                {
                    "question": "Which organization developed the SOC 2 framework?",
                    "options": ["NIST", "ISO", "AICPA", "ISACA"],
                    "correct_answer": 2
                }
            ]
        }
    },
    {
        "id": "train-grc-007",
        "title": "HIPAA Security Essentials",
        "description": "Understand HIPAA's Security Rule, the three safeguard categories, Protected Health Information (PHI) handling requirements, and breach notification obligations.",
        "category": "grc",
        "difficulty": "intermediate",
        "duration_minutes": 50,
        "tags": ["hipaa", "healthcare", "phi", "security-rule"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-grc007-01",
                "title": "HIPAA Overview & Key Rules",
                "order": 1,
                "content": "The Health Insurance Portability and Accountability Act (HIPAA) of 1996 establishes national standards for protecting sensitive patient health information.\n\nHIPAA consists of several key rules:\n\nPrivacy Rule (45 CFR Part 160 and Subparts A and E of Part 164):\n- Governs the use and disclosure of PHI in any form (electronic, paper, oral)\n- Establishes patient rights over their health information\n- Requires a Notice of Privacy Practices\n\nSecurity Rule (45 CFR Part 160 and Subparts A and C of Part 164):\n- Specifically covers electronic PHI (ePHI)\n- Requires administrative, physical, and technical safeguards\n- Mandates risk analysis and risk management\n\nBreach Notification Rule:\n- Requires notification of individuals, HHS, and potentially media following a breach of unsecured PHI\n- Defines what constitutes a breach and exceptions\n\nEnforcement Rule:\n- Establishes investigation and penalty procedures\n- Penalties range from $100 to $50,000+ per violation\n- Maximum annual penalty of $1.5 million per violation category\n\nWho must comply:\n- Covered Entities: Health plans, healthcare providers, healthcare clearinghouses\n- Business Associates: Any entity that creates, receives, maintains, or transmits PHI on behalf of a covered entity"
            },
            {
                "id": "les-grc007-02",
                "title": "The Three Safeguard Categories",
                "order": 2,
                "content": "The HIPAA Security Rule organizes its requirements into three categories of safeguards:\n\n1. Administrative Safeguards (164.308)\nPolicies and procedures designed to manage the selection, development, and implementation of security measures:\n- Security Management Process: Risk analysis and risk management\n- Assigned Security Responsibility: Designate a security official\n- Workforce Security: Authorization and access procedures\n- Information Access Management: Access control policies\n- Security Awareness and Training: Ongoing employee training\n- Security Incident Procedures: Incident response policies\n- Contingency Plan: Data backup, disaster recovery, emergency operations\n- Evaluation: Periodic technical and non-technical evaluation\n- Business Associate Contracts: Agreements with third parties\n\n2. Physical Safeguards (164.310)\nMeasures to protect electronic information systems and related buildings/equipment:\n- Facility Access Controls: Policies to limit physical access\n- Workstation Use: Policies for functions performed and physical attributes\n- Workstation Security: Physical safeguards for workstations\n- Device and Media Controls: Hardware and electronic media handling\n\n3. Technical Safeguards (164.312)\nTechnology-based measures to protect ePHI:\n- Access Control: Unique user identification, emergency access, automatic logoff, encryption\n- Audit Controls: Mechanisms to record and examine system activity\n- Integrity Controls: Policies to protect ePHI from improper alteration\n- Person or Entity Authentication: Verify identity before granting access\n- Transmission Security: Encryption and integrity controls for data in transit"
            },
            {
                "id": "les-grc007-03",
                "title": "Handling Protected Health Information (PHI)",
                "order": 3,
                "content": "Protected Health Information (PHI) includes any individually identifiable health information that is transmitted or maintained in any form.\n\n18 HIPAA Identifiers (if combined with health information, it becomes PHI):\n1. Names\n2. Geographic data smaller than a state\n3. Dates (except year) related to an individual\n4. Phone numbers\n5. Fax numbers\n6. Email addresses\n7. Social Security numbers\n8. Medical record numbers\n9. Health plan beneficiary numbers\n10. Account numbers\n11. Certificate/license numbers\n12. Vehicle identifiers and serial numbers\n13. Device identifiers and serial numbers\n14. Web URLs\n15. IP addresses\n16. Biometric identifiers\n17. Full-face photographs\n18. Any other unique identifying number or code\n\nMinimum Necessary Standard:\nCovered entities must make reasonable efforts to limit PHI to the minimum necessary to accomplish the intended purpose. This applies to:\n- Internal uses and disclosures\n- Requests to other covered entities\n- Disclosures to business associates\n\nExceptions: Treatment purposes, disclosures to the individual, and uses required by law."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How many identifiers does HIPAA define that can make health information 'PHI'?",
                    "options": ["10", "14", "18", "22"],
                    "correct_answer": 2
                },
                {
                    "question": "Which safeguard category includes risk analysis and security awareness training?",
                    "options": ["Technical Safeguards", "Physical Safeguards", "Administrative Safeguards", "Organizational Safeguards"],
                    "correct_answer": 2
                },
                {
                    "question": "What is the maximum annual penalty per violation category under HIPAA?",
                    "options": ["$100,000", "$500,000", "$1.5 million", "$10 million"],
                    "correct_answer": 2
                },
                {
                    "question": "The Minimum Necessary Standard does NOT apply to which scenario?",
                    "options": ["Internal uses", "Disclosures for treatment purposes", "Requests to other covered entities", "Disclosures to business associates"],
                    "correct_answer": 1
                }
            ]
        }
    },

    # =========================================================================
    # IRONVISION PLATFORM TRAINING
    # =========================================================================
    {
        "id": "train-plat-001",
        "title": "Getting Started with IronVision AI",
        "description": "A guided tour of the IronVision AI platform — navigating the dashboard, understanding key metrics, and finding your way around the sidebar.",
        "category": "platform",
        "difficulty": "beginner",
        "duration_minutes": 20,
        "tags": ["onboarding", "dashboard", "navigation", "getting-started"],
        "required_for_roles": ["admin", "viewer", "auditor", "manager"],
        "lessons": [
            {
                "id": "les-plat001-01",
                "title": "The Executive Dashboard",
                "order": 1,
                "content": "When you log in to IronVision AI, you land on the Executive Dashboard — your command center for organizational compliance and risk posture.\n\nKey elements:\n\nOverall Compliance Score\nThe large score at the top shows your organization's aggregate compliance percentage across all active frameworks. It's calculated as: (mapped controls / total controls) across all frameworks.\n- A+ (95-100%): Exceptional compliance posture\n- A (90-94%): Strong compliance\n- B (80-89%): Good, with room for improvement\n- C (70-79%): Moderate — action needed\n- D/F (below 70%): Significant gaps requiring immediate attention\n\nQuick Stats Row\nAt a glance, see counts for: Policies, Mappings, Open Risks, Audits, Tasks, and Vendors.\n\nFramework Compliance Chart\nA horizontal bar chart showing compliance percentage per framework. Click 'View all' to go to the Frameworks page.\n\nRisk Heatmap\nA visual 5x5 grid showing your risk distribution by likelihood and impact. Red clusters indicate areas needing urgent attention.\n\nCompliance Trend\nAn area chart showing how your compliance score has changed over time."
            },
            {
                "id": "les-plat001-02",
                "title": "Navigating the Sidebar",
                "order": 2,
                "content": "The left sidebar organizes IronVision into four main sections:\n\nOVERVIEW\n- Dashboard: Your executive compliance command center\n\nPOLICY BUILDER\n- Policy Builder: Create compliance policies using guided questionnaires\n- Document Analysis: Upload documents for AI-powered compliance analysis\n- Policy Library: View and manage all organizational policies\n- AI Mappings: Map policies to framework controls using AI\n- Cross-Framework: See how controls map across different frameworks\n\nRISK & COMPLIANCE\n- Frameworks: Browse all compliance frameworks and their controls\n- Risks: Manage your organizational risk register\n- Vendors: Track and assess third-party vendor risks\n- Audits: Plan and manage audit engagements\n\nOPERATIONS\n- Tasks: Kanban-style task management for compliance activities\n- Evidence: Centralized evidence library for audit support\n- Activity: Audit trail of all actions taken in the platform\n- Training: Compliance training modules (you are here!)\n\nBottom controls:\n- Dark Mode: Toggle between light and dark themes\n- Collapse: Minimize the sidebar for more workspace\n- User profile: Your name, email, and logout option"
            },
            {
                "id": "les-plat001-03",
                "title": "User Roles & Permissions",
                "order": 3,
                "content": "IronVision AI supports multiple user roles with different permission levels:\n\nAdmin\n- Full read/write access to all features\n- Can create, edit, and delete policies, risks, vendors, tasks, and evidence\n- Can run AI mappings and generate reports\n- Can manage user accounts and organization settings\n- Can edit and delete vendors in the Vendors section\n\nViewer (Read-Only)\n- Can view all dashboards, reports, and data\n- Cannot create, edit, or delete any records\n- Ideal for executives and stakeholders who need visibility without modification rights\n\nAuditor\n- Read access to all compliance data\n- Can add evidence and findings to audits\n- Cannot modify policies or risk assessments\n\nDemo Mode\nIronVision provides demo accounts with sample data that resets on each server restart. Look for the 'Demo Mode' badge in the top-right corner. Demo accounts cannot create new records to prevent seed data corruption."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "What does the Overall Compliance Score on the dashboard represent?",
                    "options": [
                        "The number of open risks",
                        "The percentage of mapped controls across all frameworks",
                        "The number of completed audits",
                        "Your organization's security budget utilization"
                    ],
                    "correct_answer": 1
                },
                {
                    "question": "Which sidebar section contains the Policy Builder?",
                    "options": ["Overview", "Policy Builder", "Risk & Compliance", "Operations"],
                    "correct_answer": 1
                },
                {
                    "question": "Which user role has read-only access?",
                    "options": ["Admin", "Viewer", "Auditor", "Manager"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-plat-002",
        "title": "Using the Policy Builder",
        "description": "Step-by-step guide to creating compliance policies using IronVision's questionnaire-based Policy Builder — from selecting a control family to generating a complete policy document.",
        "category": "platform",
        "difficulty": "beginner",
        "duration_minutes": 30,
        "tags": ["policy-builder", "questionnaire", "nist", "policy-creation"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-plat002-01",
                "title": "Starting a New Policy",
                "order": 1,
                "content": "The Policy Builder guides you through creating comprehensive compliance policies based on NIST 800-53 control families.\n\nStep 1: Navigate to Policy Builder\nClick 'Policy Builder' in the sidebar under the Policy Builder section.\n\nStep 2: Select a Control Family\nYou'll see all 20 NIST 800-53 control families displayed as cards. Each card shows:\n- Family abbreviation (e.g., AC, AT, AU)\n- Family name (e.g., Access Control)\n- Number of questions available\n\nClick on a family to begin the questionnaire.\n\nStep 3: Answer Questions\nThe questionnaire presents questions specific to that control family. Questions are designed to capture your organization's:\n- Current security practices and controls\n- Technology and tools in use\n- Organizational structure and responsibilities\n- Exception handling and escalation procedures\n\nTips:\n- Answer as thoroughly as possible — more detail leads to better policies\n- You don't need to complete all questions in one session\n- Save your progress at any time using the Save Draft button"
            },
            {
                "id": "les-plat002-02",
                "title": "Managing Drafts & Quality Scores",
                "order": 2,
                "content": "IronVision tracks your progress and provides quality feedback throughout the policy creation process.\n\nSaving Drafts:\n- Click 'Save Draft' at any point during the questionnaire\n- Your answers are preserved and you can resume later\n- Drafts appear on the Policy Builder home page with a status indicator\n\nQuality Score Indicator:\nAs you answer questions, a quality indicator updates in real-time:\n- Incomplete (Red): Fewer than 25% of questions answered\n- Minimal (Orange): 25-50% answered\n- Good (Yellow): 50-75% answered\n- Excellent (Green): Over 75% answered\n\nAiming for 'Excellent' quality ensures the generated policy will be comprehensive and actionable.\n\nResuming a Draft:\n1. Go to Policy Builder\n2. Find your saved draft in the list\n3. Click 'Continue' to pick up where you left off\n4. All previously saved answers will be pre-populated\n\nDeleting a Draft:\nIf you want to start over, click the delete icon next to a draft. This action is irreversible."
            },
            {
                "id": "les-plat002-03",
                "title": "Generating & Reviewing Policies",
                "order": 3,
                "content": "Once you've answered enough questions to achieve a satisfactory quality score, you can generate a formal policy document.\n\nStep 1: Review Your Answers\nBefore generation, IronVision presents a summary of all your responses. Review them carefully:\n- Ensure accuracy and completeness\n- Edit any responses that need refinement\n- Confirm the control family and scope are correct\n\nStep 2: Generate the Policy\nClick 'Generate Policy' to initiate the process. IronVision uses your answers to create a structured policy document that includes:\n- Policy title and version\n- Purpose and scope statements\n- Roles and responsibilities\n- Detailed control requirements based on your answers\n- Implementation guidelines\n- Review and update schedule\n\nStep 3: After Generation\nThe generated policy appears in your Policy Library where you can:\n- Review and edit the content\n- Set the status (Draft, Under Review, Active, Archived)\n- Map it to framework controls using AI Mappings\n- Download for external distribution\n\nNote: Policy generation uses AWS Lambda for processing. If the Lambda function isn't configured, the policy will be created with a template format based on your answers."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How many NIST 800-53 control families are available in the Policy Builder?",
                    "options": ["10", "14", "18", "20"],
                    "correct_answer": 3
                },
                {
                    "question": "What quality score level indicates over 75% of questions answered?",
                    "options": ["Incomplete", "Minimal", "Good", "Excellent"],
                    "correct_answer": 3
                },
                {
                    "question": "Where does a generated policy appear after creation?",
                    "options": ["Dashboard", "Policy Library", "Documents page", "Settings"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-plat-003",
        "title": "AI-Powered Control Mapping",
        "description": "Learn how to use IronVision's AI mapping engine to automatically match your policies to framework controls, review suggestions, and approve or reject mappings.",
        "category": "platform",
        "difficulty": "beginner",
        "duration_minutes": 25,
        "tags": ["ai", "mapping", "controls", "automation"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-plat003-01",
                "title": "How AI Mapping Works",
                "order": 1,
                "content": "IronVision's AI Mapping engine uses GPT-5.2 to analyze your policy text and automatically identify which compliance framework controls it satisfies.\n\nThe AI considers:\n- Policy content and language patterns\n- Control descriptions and requirements\n- Industry-standard mapping relationships\n- Context from your organizational profile\n\nConfidence Scores:\nEach AI-suggested mapping comes with a confidence score (0-100%):\n- 90-100%: High confidence — strong semantic match\n- 75-89%: Medium confidence — likely match, review recommended\n- Below 75%: Low confidence — manual review required\n\nMapping Sources:\n- AI-generated: Automatically suggested by the AI engine\n- Manual: Created by a user directly\n- Both types appear in the mappings view with clear source labels"
            },
            {
                "id": "les-plat003-02",
                "title": "Running an AI Mapping",
                "order": 2,
                "content": "Step-by-step guide to mapping a policy to controls:\n\n1. Navigate to AI Mappings\nClick 'AI Mappings' in the sidebar.\n\n2. Select a Policy\nChoose the policy you want to map from the dropdown. The AI will analyze the policy's full content.\n\n3. Select Target Framework\nChoose which compliance framework to map against (e.g., NIST 800-53, ISO 27001, SOC 2).\n\n4. Run the Mapping\nClick 'Run AI Mapping'. The engine will:\n- Parse the policy text\n- Compare against all controls in the selected framework\n- Generate suggested mappings with confidence scores\n- Display results sorted by confidence\n\n5. Review Results\nFor each suggested mapping:\n- Review the matched control and its description\n- Check the confidence score\n- Read the AI's reasoning for the match\n- Approve or reject the mapping\n\nTips:\n- Start with your most comprehensive policies for the best results\n- Map each policy against multiple frameworks for cross-framework coverage\n- High-confidence mappings can often be bulk-approved\n- Always review low-confidence suggestions carefully"
            },
            {
                "id": "les-plat003-03",
                "title": "Cross-Framework Mapping",
                "order": 3,
                "content": "The Cross-Framework page shows how controls relate across different compliance frameworks.\n\nFramework Relationship Heatmap:\nA visual matrix showing the strength of relationships between frameworks. Darker cells indicate more control-to-control mappings between two frameworks.\n- Click 'Show Heatmap' to expand (it's collapsible by default)\n- Hover over cells to see the exact mapping count\n\nMapping Table:\nBelow the heatmap, a detailed table lists individual control-to-control mappings:\n- Source framework and control\n- Target framework and control\n- Relationship type (Equivalent, Related, Partial)\n- Confidence score\n\nFiltering:\nUse the framework filter dropdowns to focus on specific framework pairs.\n\nUse cases:\n- Identify which NIST 800-53 controls satisfy ISO 27001 requirements\n- Determine gap areas when adopting a new framework\n- Reduce redundant control implementation across frameworks\n- Support multi-framework audit preparation"
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "What AI model powers IronVision's control mapping engine?",
                    "options": ["GPT-4", "GPT-5.2", "Claude", "Gemini"],
                    "correct_answer": 1
                },
                {
                    "question": "What confidence score range indicates a high-confidence mapping?",
                    "options": ["50-74%", "75-89%", "90-100%", "100% only"],
                    "correct_answer": 2
                },
                {
                    "question": "The Framework Relationship Heatmap on the Cross-Framework page is:",
                    "options": ["Always visible", "Collapsible by default", "Only available in admin mode", "A downloadable PDF"],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-plat-004",
        "title": "Framework & Control Drill-Down",
        "description": "Learn how to explore compliance frameworks in IronVision — from browsing all 12 frameworks down to individual controls and their Control Correlation Identifiers (CCIs).",
        "category": "platform",
        "difficulty": "beginner",
        "duration_minutes": 20,
        "tags": ["frameworks", "controls", "cci", "drill-down"],
        "required_for_roles": ["admin", "viewer", "auditor", "manager"],
        "lessons": [
            {
                "id": "les-plat004-01",
                "title": "Browsing Frameworks",
                "order": 1,
                "content": "IronVision ships with 12 pre-loaded compliance frameworks:\n\n1. NIST Cybersecurity Framework (CSF) — 108 controls\n2. NIST SP 800-53 — 190 controls across 20 families\n3. NIST SP 800-171 — 110 controls\n4. ISO 27001 — 114 controls\n5. GDPR — 99 controls\n6. HIPAA — 75 controls\n7. SOC 2 — 64 controls\n8. PCI DSS — 78 controls\n9. CMMC — 110 controls\n10. StateRAMP — 167 controls\n11. NIST AI RMF — 62 controls\n12. NIS2 — 73 controls\n\nNavigating to Frameworks:\nClick 'Frameworks' in the sidebar under Risk & Compliance.\n\nEach framework card shows:\n- Framework name and version\n- Total number of controls\n- A 'View Details' button to drill into the control list\n\nThe framework list is searchable — use the search bar at the top to quickly find a specific framework."
            },
            {
                "id": "les-plat004-02",
                "title": "Exploring Controls & CCIs",
                "order": 2,
                "content": "Drill-down path: Frameworks > Controls > CCIs\n\nViewing Controls:\nClick 'View Details' on any framework card to see its full control list. The control list shows:\n- Control ID (e.g., AC-1, AC-2)\n- Control Title\n- Control Family/Category\n\nControl Detail Page:\nClick on any control to view its detail page, which includes:\n- Full control description\n- Control family and category\n- Associated Control Correlation Identifiers (CCIs)\n\nCCI Drill-Down (NIST 800-53):\nFor NIST 800-53 controls, you can drill further into CCIs. Each CCI shows:\n- CCI ID (e.g., CCI-000001)\n- Definition — the specific, measurable requirement\n- Type — what aspect of the control it addresses\n- Status — whether it's been satisfied\n\nIronVision currently houses 243 CCIs mapped to NIST 800-53 controls, providing the most granular level of compliance tracking available.\n\nThis drill-down capability is essential for:\n- STIG compliance mapping\n- Detailed audit evidence preparation\n- Understanding exactly what each control requires at an implementation level"
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How many compliance frameworks does IronVision ship with?",
                    "options": ["8", "10", "12", "15"],
                    "correct_answer": 2
                },
                {
                    "question": "How many CCIs are currently mapped in IronVision for NIST 800-53?",
                    "options": ["100", "190", "243", "500"],
                    "correct_answer": 2
                },
                {
                    "question": "What is the drill-down path for exploring framework details?",
                    "options": [
                        "Dashboard > Frameworks > Policies",
                        "Frameworks > Controls > CCIs",
                        "Frameworks > Audits > Evidence",
                        "Risks > Controls > Mappings"
                    ],
                    "correct_answer": 1
                }
            ]
        }
    },
    {
        "id": "train-plat-005",
        "title": "Managing Risks & Vendors",
        "description": "A practical guide to using IronVision's Risk Register and Vendor Management features — creating risks, scoring them, tracking vendor assessments, and managing the full lifecycle.",
        "category": "platform",
        "difficulty": "beginner",
        "duration_minutes": 25,
        "tags": ["risks", "vendors", "risk-register", "tprm"],
        "required_for_roles": ["admin", "manager"],
        "lessons": [
            {
                "id": "les-plat005-01",
                "title": "The Risk Register",
                "order": 1,
                "content": "The Risks page is your centralized risk register for tracking all organizational risks.\n\nCreating a New Risk:\n1. Click 'Add Risk' on the Risks page\n2. Fill in the required fields:\n   - Title: Clear, concise risk name\n   - Description: Detailed risk scenario\n   - Category: Security, Compliance, Operational, Financial, Reputational\n   - Likelihood: 1 (Rare) to 5 (Almost Certain)\n   - Impact: 1 (Negligible) to 5 (Catastrophic)\n   - Status: Open, Mitigated, Accepted, Transferred, Closed\n   - Owner: Person accountable for this risk\n3. The Risk Score is automatically calculated (Likelihood x Impact)\n\nRisk Heatmap:\nThe dashboard shows a 5x5 heatmap plotting all risks by likelihood and impact. This provides an instant visual of your risk landscape.\n\nFiltering & Sorting:\n- Filter by status (Open, Mitigated, Accepted)\n- Filter by category\n- Sort by risk score to prioritize the most critical items\n\nCreating Tasks from Risks:\nFor any open risk, you can create a remediation task directly — linking the risk to an actionable work item in the Tasks Kanban board."
            },
            {
                "id": "les-plat005-02",
                "title": "Vendor Management",
                "order": 2,
                "content": "The Vendors page tracks all third-party vendors and their risk assessments.\n\nAdding a Vendor:\n1. Click 'Add Vendor'\n2. Provide:\n   - Vendor Name\n   - Contact Email\n   - Risk Level: Critical, High, Medium, Low\n   - Assessment Status: Pending, In Progress, Completed\n\nEditing & Deleting Vendors (Admin Only):\nAdministrators can:\n- Edit vendor details by clicking the edit icon on any vendor card\n- Delete vendors by clicking the delete icon (confirmation required)\n- Update risk levels and assessment statuses as assessments progress\n\nVendor Risk Levels:\n- Critical: Vendors with access to highly sensitive data or critical systems. Require quarterly reviews.\n- High: Significant data access or business dependency. Semi-annual reviews.\n- Medium: Moderate data exposure. Annual reviews.\n- Low: Minimal risk exposure. Biennial reviews.\n\nThe dashboard's Quick Stats show a count of high-risk vendors, helping leadership maintain visibility."
            }
        ],
        "quiz": {
            "passing_score": 70,
            "questions": [
                {
                    "question": "How is the Risk Score calculated in IronVision?",
                    "options": [
                        "Impact divided by Likelihood",
                        "Likelihood plus Impact",
                        "Likelihood multiplied by Impact",
                        "A weighted average algorithm"
                    ],
                    "correct_answer": 2
                },
                {
                    "question": "Who can edit and delete vendors in IronVision?",
                    "options": ["All users", "Admins only", "Auditors only", "Viewers and Admins"],
                    "correct_answer": 1
                },
                {
                    "question": "What can you create directly from an open risk?",
                    "options": ["A new policy", "A remediation task", "A vendor assessment", "An audit engagement"],
                    "correct_answer": 1
                }
            ]
        }
    }
]
