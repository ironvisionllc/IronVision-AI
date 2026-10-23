"""Synthetic, hand-labelled evaluation set for the non-XX-1 Policy Auditor. EXPECTED lists the 800-53A objective suffixes a
careful assessor would mark MET from the text; every other objective of the control is expected NOT met (deliberate gaps)."""

POLICIES = {
    "access_control": [
        "Access Control Standard (synthetic)",
        "4. AC-7 Unsuccessful logon attempts. The system enforces a limit of three consecutive invalid logon attempts by a user during a 15 minute period.",
        "Accounts are reviewed by the account manager each quarter.",
        "5. AC-11 Device lock. A device lock is initiated after 15 minutes of inactivity on every workstation.",
        "The session lock remains in place until the screen is touched.",
    ],
    "audit": [
        "Audit and Accountability Standard (synthetic)",
        "3. AU-6 Audit record review. The ISSO reviews and analyzes audit records weekly for indications of inappropriate or unusual activity.",
        "Audit review findings are reported to the ISSM and the system owner.",
        "4. AU-11 Audit record retention. Audit logs are retained to support after-the-fact investigations of security incidents.",
    ],
    "configuration": [
        "Configuration Management Standard (synthetic)",
        "2. CM-2 Baseline configuration. A current baseline configuration of the system is developed and documented by the configuration manager.",
        "The baseline configuration is maintained under configuration control by the change control board.",
        "The baseline configuration is reviewed and updated annually.",
    ],
    "incident": [
        "Incident Response Standard (synthetic)",
        "6. IR-6 Incident reporting. All personnel must report suspected incidents to the Security Operations Center within one hour of discovery.",
        "The incident response team keeps a log of every ticket.",
    ],
    "contingency": [
        "Contingency Planning Standard (synthetic)",
        "7. CP-9 System backup. Backups of user-level information on all file servers are conducted daily.",
        "Backups of system-level information are conducted weekly.",
        "Backup media are encrypted to protect the confidentiality and integrity of backup information.",
    ],
    "identification": [
        "Identification and Authentication Standard (synthetic)",
        "5. IA-5 Authenticator management. Default passwords are changed prior to first use.",
        "Passwords expire and must be changed every 60 days.",
        "Passwords must be at least 15 characters long to provide sufficient strength.",
        "Authenticator content is protected from unauthorized disclosure and modification by encryption.",
    ],
}

EXPECTED = {
    "access_control": {"ac-7": {".a"}, "ac-11": {".a"}},
    "audit": {"au-6": {".a", ".b"}, "au-11": set()},
    "configuration": {"cm-2": {".a-1", ".a-2", ".b.1"}},
    "incident": {"ir-6": {".a"}},
    "contingency": {"cp-9": {".a", ".b", ".d-1", ".d-2"}},
    "identification": {"ia-5": {".c", ".e", ".f", ".g"}},
}

PRECISION_MIN = 0.9
RECALL_MIN = 0.6
