"""
CCI (Control Correlation Identifier) data for NIST SP 800-53 controls.
Based on DISA CCI definitions. Each CCI maps to a specific aspect of a parent control.
"""

NIST_800_53_CCIS = {
    "AC-1": [
        {"cci_id": "CCI-000001", "definition": "The organization develops, documents, and disseminates an access control policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000002", "definition": "The access control policy addresses purpose, scope, roles, responsibilities, and compliance.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000003", "definition": "The organization develops, documents, and disseminates procedures to facilitate the implementation of the access control policy.", "status": "published", "type": "procedure"},
        {"cci_id": "CCI-000004", "definition": "The organization reviews and updates the current access control policy on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000005", "definition": "The organization reviews and updates the current access control procedures on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AC-2": [
        {"cci_id": "CCI-000006", "definition": "The organization manages system accounts by identifying and selecting authorized users of the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000007", "definition": "The organization assigns account managers for system accounts.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000008", "definition": "The organization establishes conditions for group and role membership.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000009", "definition": "The organization specifies authorized users of the system, group and role membership, and access authorizations for each account.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000010", "definition": "The organization requires approvals by designated personnel or roles for requests to create accounts.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000011", "definition": "The organization creates, enables, modifies, disables, and removes system accounts in accordance with organizational policy.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000012", "definition": "The organization monitors the use of system accounts.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000013", "definition": "The organization notifies account managers when accounts are no longer required or when users are terminated.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000014", "definition": "The organization authorizes access to the system based on a valid access authorization and intended system usage.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000015", "definition": "The organization reviews accounts for compliance on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AC-3": [
        {"cci_id": "CCI-000016", "definition": "The system enforces approved authorizations for logical access to information and system resources.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000017", "definition": "The system enforces approved authorizations in accordance with applicable access control policies.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000018", "definition": "Access control policies specify identity-based, role-based, or attribute-based conditions.", "status": "published", "type": "policy"},
    ],
    "AC-4": [
        {"cci_id": "CCI-000019", "definition": "The system enforces approved authorizations for controlling the flow of information within the system.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000020", "definition": "The system enforces approved authorizations for controlling the flow of information between interconnected systems.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000021", "definition": "Information flow control policies are based on organization-defined attributes associated with the information.", "status": "published", "type": "policy"},
    ],
    "AC-5": [
        {"cci_id": "CCI-000022", "definition": "The organization identifies and documents organization-defined duties of individuals requiring separation.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000023", "definition": "The organization defines system access authorizations to support separation of duties.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000024", "definition": "The system enforces separation of duties through assigned access authorizations.", "status": "published", "type": "technical"},
    ],
    "AC-6": [
        {"cci_id": "CCI-000025", "definition": "The organization employs the principle of least privilege, allowing only authorized accesses necessary to accomplish assigned tasks.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000026", "definition": "The organization authorizes access for organization-defined personnel or roles to security functions and security-relevant information.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000027", "definition": "The organization restricts privileged accounts on the system to organization-defined personnel or roles.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000028", "definition": "The system audits the execution of privileged functions.", "status": "published", "type": "monitoring"},
    ],
    "AC-7": [
        {"cci_id": "CCI-000029", "definition": "The system enforces a limit of organization-defined number of consecutive invalid logon attempts by a user.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000030", "definition": "The system automatically locks the account or delays next logon prompt when the maximum number of unsuccessful attempts is exceeded.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000031", "definition": "The system notifies the user of the number of unsuccessful logon attempts.", "status": "published", "type": "technical"},
    ],
    "AC-17": [
        {"cci_id": "CCI-000032", "definition": "The organization establishes and documents usage restrictions, configuration requirements, and implementation guidance for remote access.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000033", "definition": "The organization authorizes remote access to the system prior to allowing such connections.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000034", "definition": "The system monitors and controls remote access methods.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000035", "definition": "The system implements cryptographic mechanisms to protect the confidentiality and integrity of remote access sessions.", "status": "published", "type": "technical"},
    ],
    "AC-20": [
        {"cci_id": "CCI-000036", "definition": "The organization establishes terms and conditions for authorized individuals to access the system from external systems.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000037", "definition": "The organization permits authorized individuals to use an external system to access the system only when the organization verifies security controls.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000038", "definition": "The organization restricts or prohibits the use of organization-controlled portable storage devices on external systems.", "status": "published", "type": "implementation"},
    ],
    "AT-1": [
        {"cci_id": "CCI-000039", "definition": "The organization develops, documents, and disseminates an awareness and training policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000040", "definition": "The awareness and training policy addresses purpose, scope, roles, responsibilities, management commitment, and compliance.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000041", "definition": "The organization reviews and updates the current awareness and training policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AT-2": [
        {"cci_id": "CCI-000042", "definition": "The organization provides security and privacy literacy training to system users as part of initial training.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000043", "definition": "The organization provides security and privacy literacy training when required by system changes.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000044", "definition": "The organization provides refresher security and privacy literacy training on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000045", "definition": "The training includes recognizing and reporting potential indicators of insider threat.", "status": "published", "type": "implementation"},
    ],
    "AT-3": [
        {"cci_id": "CCI-000046", "definition": "The organization provides role-based security and privacy training to personnel with assigned security roles before authorizing access.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000047", "definition": "The organization provides role-based security and privacy training when required by system changes.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000048", "definition": "The organization provides refresher role-based security and privacy training on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AU-1": [
        {"cci_id": "CCI-000049", "definition": "The organization develops, documents, and disseminates an audit and accountability policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000050", "definition": "The audit and accountability policy addresses purpose, scope, roles, responsibilities, and compliance.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000051", "definition": "The organization reviews and updates the current audit and accountability policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AU-2": [
        {"cci_id": "CCI-000052", "definition": "The organization identifies the types of events that the system is capable of logging in support of the audit function.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000053", "definition": "The organization coordinates the event logging function with other organizational entities requiring audit-related information.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000054", "definition": "The organization reviews and updates the list of auditable events on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "AU-3": [
        {"cci_id": "CCI-000055", "definition": "The system generates audit records containing information that establishes the type of event that occurred.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000056", "definition": "The system generates audit records containing information that establishes when the event occurred.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000057", "definition": "The system generates audit records containing information that establishes where the event occurred.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000058", "definition": "The system generates audit records containing information that establishes the source of the event.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000059", "definition": "The system generates audit records containing the identity of any individuals or subjects associated with the event.", "status": "published", "type": "technical"},
    ],
    "AU-6": [
        {"cci_id": "CCI-000060", "definition": "The organization reviews and analyzes system audit records on an organization-defined frequency for indications of inappropriate activity.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000061", "definition": "The organization reports findings of audit record reviews to organization-defined personnel or roles.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000062", "definition": "The organization adjusts the level of audit record review when there is a change in risk to operations.", "status": "published", "type": "review"},
    ],
    "AU-12": [
        {"cci_id": "CCI-000063", "definition": "The system provides audit record generation capability for the auditable events defined in AU-2.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000064", "definition": "The system allows organization-defined personnel to select the auditable events to be audited by specific components.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000065", "definition": "The system generates audit records for the events defined in AU-2 with the content defined in AU-3.", "status": "published", "type": "technical"},
    ],
    "CA-1": [
        {"cci_id": "CCI-000066", "definition": "The organization develops, documents, and disseminates an assessment, authorization, and monitoring policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000067", "definition": "The organization reviews and updates the current assessment, authorization, and monitoring policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "CA-2": [
        {"cci_id": "CCI-000068", "definition": "The organization develops a control assessment plan that describes the scope of the assessment.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000069", "definition": "The organization assesses the controls in the system on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000070", "definition": "The organization produces a control assessment report that documents the results.", "status": "published", "type": "implementation"},
    ],
    "CA-3": [
        {"cci_id": "CCI-000071", "definition": "The organization approves and manages the exchange of information between the system and other systems using interconnection security agreements.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000072", "definition": "The organization documents the interface characteristics, security requirements, and the nature of the information communicated.", "status": "published", "type": "implementation"},
    ],
    "CA-7": [
        {"cci_id": "CCI-000073", "definition": "The organization develops a continuous monitoring strategy and implements a continuous monitoring program.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000074", "definition": "The organization establishes organization-defined metrics to be monitored.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000075", "definition": "The organization assesses control effectiveness on an organization-defined frequency using organization-defined assessment techniques.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000076", "definition": "The organization reports security and privacy posture of the system to organization-defined personnel on an organization-defined frequency.", "status": "published", "type": "monitoring"},
    ],
    "CM-1": [
        {"cci_id": "CCI-000077", "definition": "The organization develops, documents, and disseminates a configuration management policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000078", "definition": "The organization reviews and updates the current configuration management policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "CM-2": [
        {"cci_id": "CCI-000079", "definition": "The organization develops, documents, and maintains a current baseline configuration of the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000080", "definition": "The organization reviews and updates the baseline configuration on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000081", "definition": "The organization maintains a complete, accurate, and readily available baseline configuration.", "status": "published", "type": "implementation"},
    ],
    "CM-3": [
        {"cci_id": "CCI-000082", "definition": "The organization determines and documents the types of changes to the system that are configuration-controlled.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000083", "definition": "The organization reviews proposed configuration-controlled changes and approves or disapproves such changes.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000084", "definition": "The organization documents configuration change decisions associated with the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000085", "definition": "The organization retains records of configuration-controlled changes to the system for an organization-defined time period.", "status": "published", "type": "implementation"},
    ],
    "CM-6": [
        {"cci_id": "CCI-000086", "definition": "The organization establishes and documents configuration settings for components employed within the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000087", "definition": "The organization implements the configuration settings using the most restrictive mode consistent with operational requirements.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000088", "definition": "The organization identifies, documents, and approves any deviations from established configuration settings.", "status": "published", "type": "review"},
    ],
    "CM-7": [
        {"cci_id": "CCI-000089", "definition": "The organization configures the system to provide only organization-defined mission essential capabilities.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000090", "definition": "The organization prohibits or restricts the use of organization-defined functions, ports, protocols, and services.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000091", "definition": "The organization reviews the system on an organization-defined frequency to identify unnecessary functions, ports, protocols, and services.", "status": "published", "type": "review"},
    ],
    "CM-8": [
        {"cci_id": "CCI-000092", "definition": "The organization develops and documents an inventory of system components that accurately reflects the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000093", "definition": "The organization reviews and updates the system component inventory on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000094", "definition": "The inventory includes information deemed necessary to achieve effective property accountability.", "status": "published", "type": "implementation"},
    ],
    "CP-1": [
        {"cci_id": "CCI-000095", "definition": "The organization develops, documents, and disseminates a contingency planning policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000096", "definition": "The organization reviews and updates the current contingency planning policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "CP-2": [
        {"cci_id": "CCI-000097", "definition": "The organization develops a contingency plan for the system that identifies essential mission and business functions.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000098", "definition": "The contingency plan provides recovery objectives, restoration priorities, and metrics.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000099", "definition": "The organization distributes copies of the contingency plan to organization-defined key contingency personnel.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000100", "definition": "The organization reviews the contingency plan on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "CP-9": [
        {"cci_id": "CCI-000101", "definition": "The organization conducts backups of user-level information contained in the system on an organization-defined frequency.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000102", "definition": "The organization conducts backups of system-level information on an organization-defined frequency.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000103", "definition": "The organization conducts backups of system documentation on an organization-defined frequency.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000104", "definition": "The organization protects the confidentiality, integrity, and availability of backup information.", "status": "published", "type": "technical"},
    ],
    "IA-1": [
        {"cci_id": "CCI-000105", "definition": "The organization develops, documents, and disseminates an identification and authentication policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000106", "definition": "The organization reviews and updates the current identification and authentication policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "IA-2": [
        {"cci_id": "CCI-000107", "definition": "The system uniquely identifies and authenticates organizational users.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000108", "definition": "The system implements multi-factor authentication for network access to privileged accounts.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000109", "definition": "The system implements multi-factor authentication for network access to non-privileged accounts.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000110", "definition": "The system implements multi-factor authentication for local access to privileged accounts.", "status": "published", "type": "technical"},
    ],
    "IA-4": [
        {"cci_id": "CCI-000111", "definition": "The organization manages system identifiers by receiving authorization from organization-defined personnel to assign identifiers.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000112", "definition": "The organization selects an identifier that identifies an individual, group, role, service, or device.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000113", "definition": "The organization prevents reuse of identifiers for an organization-defined time period.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000114", "definition": "The organization disables the identifier after an organization-defined time period of inactivity.", "status": "published", "type": "implementation"},
    ],
    "IA-5": [
        {"cci_id": "CCI-000115", "definition": "The organization manages system authenticators by verifying the identity of the individual receiving the authenticator.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000116", "definition": "The organization establishes initial authenticator content for authenticators defined by the organization.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000117", "definition": "The organization ensures that authenticators have sufficient strength of mechanism for their intended use.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000118", "definition": "The organization changes default authenticators prior to first use.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000119", "definition": "The organization protects authenticator content from unauthorized disclosure and modification.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000120", "definition": "The organization requires individuals to take specific security safeguards to protect authenticators.", "status": "published", "type": "implementation"},
    ],
    "IR-1": [
        {"cci_id": "CCI-000121", "definition": "The organization develops, documents, and disseminates an incident response policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000122", "definition": "The incident response policy addresses purpose, scope, roles, responsibilities, management commitment, and compliance.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000123", "definition": "The organization reviews and updates the current incident response policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "IR-2": [
        {"cci_id": "CCI-000124", "definition": "The organization provides incident response training to system users consistent with assigned roles.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000125", "definition": "The organization provides incident response training when required by system changes.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000126", "definition": "The organization provides refresher incident response training on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "IR-4": [
        {"cci_id": "CCI-000127", "definition": "The organization implements an incident handling capability for incidents that includes preparation, detection, analysis, containment, eradication, and recovery.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000128", "definition": "The organization coordinates incident handling activities with contingency planning activities.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000129", "definition": "The organization incorporates lessons learned from ongoing incident handling activities into incident response procedures.", "status": "published", "type": "review"},
    ],
    "IR-5": [
        {"cci_id": "CCI-000130", "definition": "The organization tracks and documents system security incidents.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000131", "definition": "The organization maintains records of system security incidents with sufficient detail.", "status": "published", "type": "implementation"},
    ],
    "IR-6": [
        {"cci_id": "CCI-000132", "definition": "The organization requires personnel to report suspected incidents to the organizational incident response capability within an organization-defined time period.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000133", "definition": "The organization reports incident information to organization-defined authorities.", "status": "published", "type": "implementation"},
    ],
    "PE-1": [
        {"cci_id": "CCI-000134", "definition": "The organization develops, documents, and disseminates a physical and environmental protection policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000135", "definition": "The organization reviews and updates the current physical and environmental protection policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PE-2": [
        {"cci_id": "CCI-000136", "definition": "The organization develops, approves, and maintains a list of individuals with authorized access to the facility.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000137", "definition": "The organization issues authorization credentials for facility access.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000138", "definition": "The organization reviews the access list detailing authorized facility access on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PE-3": [
        {"cci_id": "CCI-000139", "definition": "The organization enforces physical access authorizations at entry and exit points to the facility.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000140", "definition": "The organization maintains physical access audit logs for entry and exit points.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000141", "definition": "The organization controls physical access to organization-defined areas within the facility designated as publicly accessible.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000142", "definition": "The organization escorts visitors and monitors visitor activity.", "status": "published", "type": "implementation"},
    ],
    "RA-1": [
        {"cci_id": "CCI-000143", "definition": "The organization develops, documents, and disseminates a risk assessment policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000144", "definition": "The organization reviews and updates the current risk assessment policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "RA-3": [
        {"cci_id": "CCI-000145", "definition": "The organization conducts an assessment of risk that identifies threats to and vulnerabilities in the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000146", "definition": "The organization determines the likelihood and magnitude of harm from unauthorized access, use, disclosure, disruption, modification, or destruction.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000147", "definition": "The organization documents risk assessment results.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000148", "definition": "The organization reviews risk assessment results on an organization-defined frequency.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000149", "definition": "The organization updates the risk assessment on an organization-defined frequency or when significant changes occur.", "status": "published", "type": "review"},
    ],
    "RA-5": [
        {"cci_id": "CCI-000150", "definition": "The organization scans for vulnerabilities in the system on an organization-defined frequency.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000151", "definition": "The organization employs vulnerability monitoring tools that facilitate interoperability among tools.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000152", "definition": "The organization analyzes vulnerability scan reports and results from security assessments.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000153", "definition": "The organization remediates legitimate vulnerabilities in accordance with an organizational assessment of risk.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000154", "definition": "The organization shares information obtained from the vulnerability monitoring process with organization-defined personnel.", "status": "published", "type": "monitoring"},
    ],
    "SA-1": [
        {"cci_id": "CCI-000155", "definition": "The organization develops, documents, and disseminates a system and services acquisition policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000156", "definition": "The organization reviews and updates the current system and services acquisition policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "SA-3": [
        {"cci_id": "CCI-000157", "definition": "The organization manages the system using a system development life cycle methodology.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000158", "definition": "The organization defines and documents information security roles and responsibilities throughout the system development life cycle.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000159", "definition": "The organization identifies individuals having information security roles and responsibilities.", "status": "published", "type": "implementation"},
    ],
    "SA-4": [
        {"cci_id": "CCI-000160", "definition": "The organization includes security and privacy functional requirements in the acquisition contract for the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000161", "definition": "The organization includes security and privacy strength requirements in the acquisition contract.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000162", "definition": "The organization includes security and privacy documentation requirements in the acquisition contract.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000163", "definition": "The organization requires the developer to provide a description of the system development environment and controls employed.", "status": "published", "type": "implementation"},
    ],
    "SC-1": [
        {"cci_id": "CCI-000164", "definition": "The organization develops, documents, and disseminates a system and communications protection policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000165", "definition": "The organization reviews and updates the current system and communications protection policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "SC-7": [
        {"cci_id": "CCI-000166", "definition": "The system monitors and controls communications at the external managed interfaces to the system.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000167", "definition": "The system monitors and controls communications at key internal managed interfaces.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000168", "definition": "The system implements subnetworks for publicly accessible system components that are physically or logically separated from internal networks.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000169", "definition": "The system connects to external networks only through managed interfaces consisting of boundary protection devices.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000170", "definition": "The system limits the number of external network connections to the system.", "status": "published", "type": "technical"},
    ],

    # MA – Maintenance
    "MA-1": [
        {"cci_id": "CCI-000171", "definition": "The organization develops, documents, and disseminates a system maintenance policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000172", "definition": "The organization reviews and updates the current system maintenance policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "MA-2": [
        {"cci_id": "CCI-000173", "definition": "The organization schedules, performs, documents, and reviews records of maintenance and repairs on system components.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000174", "definition": "The organization approves and monitors all maintenance activities, whether performed on site or remotely.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000175", "definition": "The organization ensures that maintenance records are maintained for organization-defined system components.", "status": "published", "type": "implementation"},
    ],
    "MA-3": [
        {"cci_id": "CCI-000176", "definition": "The organization approves, controls, and monitors the use of system maintenance tools.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000177", "definition": "The organization checks maintenance tools for improper or unauthorized modifications.", "status": "published", "type": "review"},
    ],
    "MA-4": [
        {"cci_id": "CCI-000178", "definition": "The organization authorizes, monitors, and controls nonlocal maintenance and diagnostic activities.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000179", "definition": "The organization requires strong authentication for nonlocal maintenance sessions.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000180", "definition": "The organization terminates session and network connections when nonlocal maintenance is completed.", "status": "published", "type": "technical"},
    ],
    "MA-5": [
        {"cci_id": "CCI-000181", "definition": "The organization establishes a process for maintenance personnel authorization and maintains a list of authorized organizations or personnel.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000182", "definition": "The organization ensures that non-escorted personnel performing maintenance have required access authorizations.", "status": "published", "type": "implementation"},
    ],

    # MP – Media Protection
    "MP-1": [
        {"cci_id": "CCI-000183", "definition": "The organization develops, documents, and disseminates a media protection policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000184", "definition": "The organization reviews and updates the current media protection policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "MP-2": [
        {"cci_id": "CCI-000185", "definition": "The organization restricts access to organization-defined types of digital and non-digital media to authorized personnel.", "status": "published", "type": "implementation"},
    ],
    "MP-4": [
        {"cci_id": "CCI-000186", "definition": "The organization physically controls and securely stores digital and non-digital media within controlled areas.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000187", "definition": "The organization protects system media until media are destroyed or sanitized using approved procedures.", "status": "published", "type": "implementation"},
    ],
    "MP-6": [
        {"cci_id": "CCI-000188", "definition": "The organization sanitizes system media prior to disposal, release out of organizational control, or release for reuse.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000189", "definition": "The organization employs sanitization mechanisms with the strength and integrity commensurate with the classification of the information.", "status": "published", "type": "technical"},
    ],

    # PL – Planning
    "PL-1": [
        {"cci_id": "CCI-000190", "definition": "The organization develops, documents, and disseminates a planning policy that addresses purpose, scope, and roles.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000191", "definition": "The organization reviews and updates the current planning policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PL-2": [
        {"cci_id": "CCI-000192", "definition": "The organization develops a security plan for the system that describes the operational environment and security requirements.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000193", "definition": "The organization distributes copies of the security plan and communicates subsequent changes to designated personnel.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000194", "definition": "The organization reviews the security plan on an organization-defined frequency and updates it to address changes.", "status": "published", "type": "review"},
    ],
    "PL-4": [
        {"cci_id": "CCI-000195", "definition": "The organization establishes and makes readily available rules describing responsibilities and expected behavior for system use.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000196", "definition": "The organization receives a signed acknowledgment from individuals indicating they have read and agree to the rules of behavior.", "status": "published", "type": "implementation"},
    ],

    # PM – Program Management
    "PM-1": [
        {"cci_id": "CCI-000197", "definition": "The organization develops and disseminates an organization-wide information security program plan.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000198", "definition": "The organization reviews the information security program plan on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PM-2": [
        {"cci_id": "CCI-000199", "definition": "The organization appoints a senior information security officer with the mission and resources to manage the security program.", "status": "published", "type": "implementation"},
    ],
    "PM-9": [
        {"cci_id": "CCI-000200", "definition": "The organization develops a comprehensive strategy to manage risk to organizational operations and assets.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000201", "definition": "The risk management strategy is consistently applied across the organization.", "status": "published", "type": "implementation"},
    ],

    # PS – Personnel Security
    "PS-1": [
        {"cci_id": "CCI-000202", "definition": "The organization develops, documents, and disseminates a personnel security policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000203", "definition": "The organization reviews and updates the current personnel security policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PS-2": [
        {"cci_id": "CCI-000204", "definition": "The organization assigns a risk designation to all organizational positions.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000205", "definition": "The organization establishes screening criteria for individuals filling organizational positions.", "status": "published", "type": "implementation"},
    ],
    "PS-3": [
        {"cci_id": "CCI-000206", "definition": "The organization screens individuals prior to authorizing access to the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000207", "definition": "The organization rescreens individuals on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PS-4": [
        {"cci_id": "CCI-000208", "definition": "The organization, upon termination, disables system access within an organization-defined time period.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000209", "definition": "The organization retrieves all security-related organizational system-related property upon termination.", "status": "published", "type": "implementation"},
    ],
    "PS-5": [
        {"cci_id": "CCI-000210", "definition": "The organization reviews and confirms ongoing operational need for current access authorizations when personnel are transferred.", "status": "published", "type": "review"},
    ],
    "PS-6": [
        {"cci_id": "CCI-000211", "definition": "The organization develops and documents access agreements for organizational systems.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000212", "definition": "The organization reviews and updates access agreements on an organization-defined frequency.", "status": "published", "type": "review"},
    ],

    # PT – PII Processing and Transparency
    "PT-1": [
        {"cci_id": "CCI-000213", "definition": "The organization develops, documents, and disseminates a PII processing and transparency policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000214", "definition": "The organization reviews and updates the PII processing and transparency policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "PT-2": [
        {"cci_id": "CCI-000215", "definition": "The organization determines and documents the legal authority that permits the collection, use, and sharing of PII.", "status": "published", "type": "implementation"},
    ],
    "PT-3": [
        {"cci_id": "CCI-000216", "definition": "The organization identifies and documents the specific purpose for processing PII.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000217", "definition": "The organization describes the purpose for processing PII in the public privacy notices and policies.", "status": "published", "type": "implementation"},
    ],
    "PT-5": [
        {"cci_id": "CCI-000218", "definition": "The organization provides clear and accessible notice to individuals about the processing of their PII.", "status": "published", "type": "implementation"},
    ],

    # SI – System and Information Integrity
    "SI-1": [
        {"cci_id": "CCI-000219", "definition": "The organization develops, documents, and disseminates a system and information integrity policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000220", "definition": "The organization reviews and updates the current system and information integrity policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "SI-2": [
        {"cci_id": "CCI-000221", "definition": "The organization identifies, reports, and corrects system flaws.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000222", "definition": "The organization tests software and firmware updates related to flaw remediation before installation.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000223", "definition": "The organization installs security-relevant software and firmware updates within an organization-defined time period.", "status": "published", "type": "technical"},
    ],
    "SI-3": [
        {"cci_id": "CCI-000224", "definition": "The organization implements malicious code protection mechanisms at system entry and exit points.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000225", "definition": "The organization updates malicious code protection mechanisms when new releases are available.", "status": "published", "type": "technical"},
        {"cci_id": "CCI-000226", "definition": "The system blocks, quarantines, or alerts the administrator in response to malicious code detection.", "status": "published", "type": "technical"},
    ],
    "SI-4": [
        {"cci_id": "CCI-000227", "definition": "The organization monitors the system to detect attacks, indicators of potential attacks, and unauthorized connections.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000228", "definition": "The organization identifies unauthorized use of the system through monitoring.", "status": "published", "type": "monitoring"},
        {"cci_id": "CCI-000229", "definition": "The organization deploys monitoring devices strategically within the system to collect organization-determined essential information.", "status": "published", "type": "technical"},
    ],
    "SI-5": [
        {"cci_id": "CCI-000230", "definition": "The organization receives system security alerts, advisories, and directives from designated external organizations.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000231", "definition": "The organization generates and disseminates internal security alerts, advisories, and directives as deemed necessary.", "status": "published", "type": "implementation"},
    ],
    "SI-7": [
        {"cci_id": "CCI-000232", "definition": "The organization employs integrity verification tools to detect unauthorized changes to software, firmware, and information.", "status": "published", "type": "technical"},
    ],
    "SI-10": [
        {"cci_id": "CCI-000233", "definition": "The system checks the validity of organization-defined information inputs.", "status": "published", "type": "technical"},
    ],
    "SI-12": [
        {"cci_id": "CCI-000234", "definition": "The organization manages and retains information within the system in accordance with applicable laws and policies.", "status": "published", "type": "implementation"},
    ],

    # SR – Supply Chain Risk Management
    "SR-1": [
        {"cci_id": "CCI-000235", "definition": "The organization develops, documents, and disseminates a supply chain risk management policy.", "status": "published", "type": "policy"},
        {"cci_id": "CCI-000236", "definition": "The organization reviews and updates the supply chain risk management policy on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "SR-2": [
        {"cci_id": "CCI-000237", "definition": "The organization develops a plan for managing supply chain risks associated with the system.", "status": "published", "type": "implementation"},
        {"cci_id": "CCI-000238", "definition": "The supply chain risk management plan addresses threats, vulnerabilities, and risk mitigation activities.", "status": "published", "type": "implementation"},
    ],
    "SR-3": [
        {"cci_id": "CCI-000239", "definition": "The organization establishes a process for identifying and addressing weaknesses or deficiencies in supply chain elements.", "status": "published", "type": "implementation"},
    ],
    "SR-5": [
        {"cci_id": "CCI-000240", "definition": "The organization employs acquisition strategies, contract tools, and procurement methods to protect against supply chain risks.", "status": "published", "type": "implementation"},
    ],
    "SR-6": [
        {"cci_id": "CCI-000241", "definition": "The organization assesses and reviews the supply chain-related risks associated with suppliers.", "status": "published", "type": "review"},
        {"cci_id": "CCI-000242", "definition": "The organization conducts supplier assessments on an organization-defined frequency.", "status": "published", "type": "review"},
    ],
    "SR-11": [
        {"cci_id": "CCI-000243", "definition": "The organization develops and implements anti-counterfeit policy for the detection and prevention of counterfeit components.", "status": "published", "type": "implementation"},
    ],
}


def get_ccis_for_control(control_id: str):
    """Get all CCIs for a given NIST 800-53 control ID."""
    return NIST_800_53_CCIS.get(control_id, [])


def get_all_ccis():
    """Get all CCIs with their parent control IDs."""
    all_ccis = []
    for control_id, ccis in NIST_800_53_CCIS.items():
        for cci in ccis:
            all_ccis.append({**cci, "parent_control_id": control_id})
    return all_ccis
