import re
import time
from typing import List, Dict, Tuple, Set, Optional
from lxml import etree
from functools import wraps
from run_resources import analysis_scope, within_run
from document_core import (parse_xml, normalize_xml, safe_parser, visible_text, rewrite_element,
    rewrite_slots, local_name, tmx_languages, tmx_variant, checked_zip, word_paragraphs, W_NS)


CLINICAL_TRIAL_PATTERNS = {
    "NCT_ID": r"\bNCT\d{8}\b",
    "EUDRACT_ID": r"\b\d{4}-\d{6}-\d{2}\b",
    "EU_CT_ID": r"\bEU[-\s]?CT\s*\d{4}[-\s]?\d{4,6}[-\s]?\d{2}[-\s]?\d{2}\b",
    "ISRCTN_ID": r"\bISRCTN\d{8}\b",
    "JRCT_ID": r"\bjRCT[a-zA-Z]?\d{7,10}\b",
    "CTRI_ID": r"\bCTRI[/\-]\d{4}[/\-]\d{2,3}[/\-]\d{5,6}\b",
    "ANZCTR_ID": r"\bACTRN\d{14}\b",
    "CHICTR_ID": r"\bChiCTR[-]?(?:[A-Z]{2,4}[-]?)?\d{7,10}\b",
    "DRKS_ID": r"\bDRKS\d{8}\b",
    "IRCT_ID": r"\bIRCT\d{14,}\b",
    "UMIN_ID": r"\bUMIN\d{9}\b",
    "KCT_ID": r"\bKCT\d{7}\b",
    "PROTOCOL_ID": r"\b(?:Protocol(?:\s+ID)?|Study)[\s:]*[A-Z]{2,5}[-\s]?\d{3,5}\b",
    "SUBJECT_ID": r"\b(?:Subject|Patient|SUBJ)[\s#:-]*\d{3,}(?:[-]\d{3})?\b",
    "SITE_NUMBER": r"\b(?:Site|Center)[\s#:-]*\d{2,4}\b",
    "LOT_BATCH_ID": r"\b(?:Lot|Batch|Kit)[\s:]*[A-Z0-9]{2,}[-]?[A-Z0-9]{2,}\b|(?:Sample(?:\s+ID))[\s:]*[A-Z0-9]{2,}[-]?[A-Z0-9]{2,}\b",
    "STRUCTURED_ID": r"\b[A-Z]{2,6}[-_/]\d{2,8}\b",
    "STRUCTURED_ID_NUM_FIRST": r"\b\d{2,6}[-_/][A-Z]{2,6}\b",
    "PRODUCT_CODE": r"\b[A-Z]{2,5}[-][A-Z]{2,5}[-][A-Z0-9]{2,5}(?:[-][A-Z0-9]{1,3})?\b",
    "NIF_CIF_ES": r"\b(?:NIF|CIF|DNI|NIE)[\s:.-]*[A-Z]?\d{7,8}[-]?[A-Z]?\b",
    "NIF_STANDALONE": r"\b[A-Z]\d{7,8}[-]?[A-Z]?\b",
    "DNI_STANDALONE": r"\b\d{8}[-]?[A-Za-z]\b",
    "LONG_NUMBER_ID": r"\b\d{3,}(?:[-./]\d{2,})+\b|\b\d{6,}[A-Za-z]*\b",
    "LICENSE_PLATE": r"\b\d{4}[\s-]?[A-Z]{2,3}\b|\b[A-Z]{1,2}[\s-]?\d{4}[\s-]?[A-Z]{2,3}\b",
    "IBAN_CODE": r"\b[A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{0,4}\b",
    "SPACED_DIGIT_SEQ": r"\b\d{2,}(?:\s\d{2,}){2,}\b",
}

CASE_SENSITIVE_PATTERNS = {
    "ALPHANUMERIC_CODE": r"\b[A-Z]{1,}\d{6,}[A-Za-z0-9]*\b|\b[A-Z]{3,}\d{5,}\b",
}

SAFE_ACRONYMS = {
    "DNA", "RNA", "mRNA", "cDNA", "siRNA", "miRNA", "tRNA", "rRNA",
    "PCR", "qPCR", "ELISA", "HPLC", "GLP", "GMP", "GCP", "ICH",
    "AUC", "BMI", "ECG", "EKG", "MRI", "PET", "CBC", "WBC", "RBC",
    "HIV", "AIDS", "HBV", "HCV", "HPV", "CMV", "EBV", "RSV", "HSV",
    "SAE", "ADE", "ADR", "SUSAR", "DLT", "MTD", "ORR", "DOR",
    "PFS", "DFS", "RFS", "TTR", "TTP", "HRR",
    "SARS", "COVID", "RECIST", "WHO", "FDA", "EMA", "TGA", "ICF", "SAP",
    "ITT", "PPS", "FAS", "SOC", "MedDRA", "CTCAE",
    "BID", "TID", "QID", "QHS", "PRN",
    "IND", "NDA", "BLA", "MAA", "CTA", "CSR",
    "SOC", "IEC", "IRB", "DMC", "CRF", "eCRF",
    "PII", "PHI", "HIPAA", "GDPR",
    "PDF", "XML", "HTML", "CSS", "SQL", "API", "URL", "HTTP", "HTTPS",
    "UTC", "GMT", "ISO", "ICD", "CPT", "ATC",
    "QOL", "VAS", "NYHA", "ECOG", "FACT",
    "NOT", "AND", "FOR", "THE", "HAS", "HAD", "ARE", "WAS", "HER",
    "HIS", "OUR", "ALL", "BUT", "NOR", "YET", "ANY", "CAN", "MAY",
    "USE", "PER", "VIA", "SET", "GET", "PUT", "RUN", "END",
    "USA", "EUR", "GBP", "USD",
    "NOTE", "ALSO", "MUST", "WILL", "DOES", "EACH", "BOTH", "ONLY",
    "WHEN", "THEN", "THAN", "SUCH", "THAT", "THIS", "WHAT", "WITH",
    "FROM", "INTO", "OVER", "SOME", "BEEN", "HAVE", "WERE", "HERE",
    "USED", "ONCE", "TYPE", "FORM", "PART", "SIDE", "SAME", "LAST",
    "NEXT", "FULL", "MADE", "CASE", "MORE", "MOST", "LESS", "VERY",
    "WELL", "JUST", "LIKE", "ALSO", "EVEN", "BACK", "LONG", "HIGH",
    "STILL", "AFTER", "ABOUT", "ABOVE", "BELOW", "UNDER", "OTHER",
    "EVERY", "FIRST", "FOUND", "GIVEN", "BASED", "USING", "WHILE",
    "THESE", "THOSE", "WHICH", "WHERE", "THERE", "THEIR", "SHALL",
    "WOULD", "COULD", "SHOULD", "BEING", "DURING", "BEFORE",
    "BETWEEN", "HOWEVER", "WITHOUT", "THROUGH", "AGAINST", "BECAUSE",
    "ANOTHER", "WHETHER", "WITHIN", "EITHER", "NEITHER",
    "TOTAL", "TABLE", "VALUE", "LEVEL", "GROUP", "STUDY", "TRIAL",
    "PHASE", "VISIT", "DAILY", "PRIOR", "AFTER", "EARLY", "FINAL",
    "MAJOR", "MINOR", "UPPER", "LOWER", "LOCAL", "POINT", "RANGE",
    "SCORE", "RATIO", "ORGAN", "BLOOD", "LIVER", "RENAL", "VIRAL",
}



# Stopwords funcionales (solo palabras gramaticales comunes) - v10.0
STOPWORDS_FUNCTIONAL_EN = {
    "the", "a", "an", "this", "that", "these", "those",
    "of", "in", "on", "at", "to", "from", "by", "for", "with", "as", "into", "over", "under", "between", "through",
    "and", "or", "but", "nor", "so", "yet", "if", "because", "although", "while",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs",
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "all", "any", "some", "each", "every", "no", "not", "none", "both", "either", "neither",
    "very", "too", "also", "just", "only", "even", "still", "already"
}

STOPWORDS_FUNCTIONAL_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras",
    "de", "del", "en", "a", "por", "para", "con", "sin", "sobre", "entre", "desde", "hasta", "hacia",
    "y", "o", "pero", "ni", "aunque", "porque", "si", "mientras",
    "yo", "tú", "él", "ella", "nosotros", "nosotras", "vosotros", "vosotras", "ellos", "ellas",
    "me", "te", "se", "nos", "os", "lo", "le", "les",
    "es", "son", "era", "eran", "fue", "ser", "estar",
    "he", "has", "ha", "hemos", "han", "haber",
    "todo", "toda", "todos", "todas", "algún", "alguna", "algunos", "algunas",
    "ningún", "ninguna", "ningunos", "ningunas", "no"
}

# Sustantivos comunes que suelen aparecer capitalizados por estilo (falsos positivos frecuentes)
COMMON_SINGLETON_BLOCK_EN = {
    "system", "study", "protocol", "trial", "switch", "data", "process",
    "document", "file", "report", "table", "section", "chapter", "version",
    "note", "warning", "caution", "important", "example", "figure", "appendix",
    "patient", "treatment", "medication", "disease", "adverse", "event", "consent",
    "endpoint", "efficacy", "safety", "drug", "dose", "subject", "placebo",
    "sample", "analysis", "result", "outcome", "therapy", "diagnosis", "symptom",
    "procedure", "baseline", "screening", "randomization", "cohort", "arm",
    "visit", "investigator", "sponsor", "monitor", "deviation", "amendment",
    "inclusion", "exclusion", "enrollment", "withdrawal", "discontinuation",
    "toxicity", "tolerability", "pharmacokinetics", "bioavailability",
    "compliance", "regulation", "submission", "approval", "authorization",
    "agreement", "contract", "liability", "indemnification", "confidentiality",
    "disclosure", "obligation", "jurisdiction", "arbitration", "governance",
    "oversight", "audit", "inspection", "certificate", "license", "patent",
    "trademark", "regulatory", "guideline", "directive", "statute", "provision",
    "clause", "warranty", "termination", "notification", "declaration",
    "assessment", "evaluation", "monitoring", "surveillance", "pharmacovigilance",
    "response", "infection", "inflammation", "mortality", "morbidity", "survival",
    "incidence", "prevalence", "population", "intervention", "comparator",
}

COMMON_SINGLETON_BLOCK_ES = {
    "sistema", "estudio", "protocolo", "ensayo", "cambio", "interruptor", "datos", "proceso",
    "documento", "archivo", "informe", "tabla", "sección", "capítulo", "versión",
    "nota", "advertencia", "precaución", "importante", "ejemplo", "figura", "apéndice",
    "paciente", "tratamiento", "medicación", "enfermedad", "adverso", "evento",
    "consentimiento", "eficacia", "seguridad", "fármaco", "dosis", "sujeto", "placebo",
    "muestra", "análisis", "resultado", "terapia", "diagnóstico", "síntoma",
    "procedimiento", "aleatorización", "cohorte", "brazo", "visita",
    "investigador", "promotor", "monitor", "desviación", "enmienda",
    "inclusión", "exclusión", "reclutamiento", "retirada", "discontinuación",
    "toxicidad", "tolerabilidad", "farmacocinética", "biodisponibilidad",
    "cumplimiento", "regulación", "presentación", "aprobación", "autorización",
    "acuerdo", "contrato", "responsabilidad", "indemnización", "confidencialidad",
    "divulgación", "obligación", "jurisdicción", "arbitraje", "gobernanza",
    "supervisión", "auditoría", "inspección", "certificado", "licencia", "patente",
    "regulatorio", "directriz", "directiva", "estatuto", "disposición",
    "cláusula", "garantía", "rescisión", "notificación", "declaración",
    "evaluación", "monitorización", "vigilancia", "farmacovigilancia",
    "respuesta", "infección", "inflamación", "mortalidad", "morbilidad",
    "supervivencia", "incidencia", "prevalencia", "población", "intervención",
    "comparador",
}

# NER "fuerte" que permitimos (si hay NER, no bloqueamos por listas)

CLINICAL_ABBREVIATIONS_WITH_VALUE = [
    r"\b(?:CRN|MRN|PRN|IFU|HDD|SSN|ID|REF|NO)[-#:\s]+[A-Z0-9]{2,}[-]?\d{2,}\b",
    r"\b(?:Protocol|Study|Subject|Patient|Site|Center|Kit|Vial)[-\s]*(?:ID|No|Number|#)?[-:\s]*[A-Z0-9]{2,}[-/]?\d{2,}\b",
    r"\bSample[-\s]+(?:ID|No|Number|#)[-:\s]*[A-Z0-9]{2,}[-/]?\d{2,}\b",
]

PHARMA_COMPANY_PATTERNS = [
    r"\b(?:Pfizer|Novartis|Roche|Sanofi|Merck|MSD|AstraZeneca|GSK|GlaxoSmithKline|Johnson\s*&?\s*Johnson|J&J|AbbVie|Bristol[- ]?Myers[- ]?Squibb|BMS|Eli\s*Lilly|Lilly|Amgen|Gilead|Bayer|Novo\s*Nordisk|Takeda|Boehringer\s*Ingelheim|Boehringer|Biogen|Regeneron|Moderna|BioNTech)\b",
    r"\b(?:Teva|Viatris|CSL\s*Behring|CSL|Astellas|Daiichi\s*Sankyo|Otsuka|Eisai|Chugai|Kyowa\s*Kirin|Shionogi|Alexion|Vertex|Incyte|BioMarin|Alnylam|Seagen|Horizon|UCB|Ipsen|Lundbeck|Grifols|Ferring|Servier|Menarini|Chiesi|Almirall|Gr[üu]nenthal|Fresenius|Bausch\s*Health|Jazz\s*Pharma|Hikma|Lupin|Cipla|Zydus|Sun\s*Pharma|Dr\.?\s*Reddy|Celltrion|Samsung\s*Bioepis)\b",
]

CRO_PATTERNS = [
    r"\b(?:IQVIA|Covance|PPD|ICON|Syneos\s*Health|Syneos|Parexel|PRA\s*Health|Quintiles|Labcorp|LabCorp|Charles\s*River)\b",
    r"\b(?:Medpace|Fortrea|WuXi\s*AppTec|WuXi|Caidya|Clinipace|dMed|Novotech|Ergomed|Allucent|Veristat|Synteract|CTI\s*Clinical|Inotiv|Velocity\s*Clinical|CMIC|EPS\s*International|Worldwide\s*Clinical\s*Trials|Thermo\s*Fisher|Q2\s*Solutions|Frontage|Celerion|SGS|Almac|Eurofins|Quest\s*Diagnostics)\b",
]

BLOCKBUSTER_DRUGS = [
    r"\b(?:Keytruda|pembrolizumab|Ozempic|Wegovy|semaglutide|Dupixent|dupilumab|Biktarvy|Eliquis|apixaban|Skyrizi|risankizumab|Mounjaro|Zepbound|tirzepatide|Darzalex|daratumumab|Stelara|ustekinumab|Trikafta|Kaftrio|Alyftrek)\b",
    r"\b(?:Opdivo|nivolumab|Humira|adalimumab|Eylea|aflibercept|Rinvoq|upadacitinib|Xtandi|enzalutamide|Imbruvica|ibrutinib|Tagrisso|osimertinib|Revlimid|lenalidomide|Tremfya|guselkumab|Cosentyx|secukinumab|Entresto|sacubitril)\b",
    r"\b(?:Xarelto|rivaroxaban|Trulicity|dulaglutide|Jardiance|empagliflozin|Farxiga|dapagliflozin|Ocrevus|ocrelizumab|Vyndaqel|Vyndamax|tafamidis|Paxlovid|nirmatrelvir|Comirnaty|Spikevax|Prevnar|Shingrix|Gardasil)\b",
    r"\b(?:Kisunla|donanemab|Leqembi|lecanemab|Rezdiffra|resmetirom|Datroway|Pluvicto|Enhertu|Padcev|Tecvayli|Talvey|Columvi|glofitamab|Epkinly|epcoritamab|Elahere|mirvetuximab)\b",
]

CLINICAL_TECH_PLATFORMS = [
    r"\b(?:Veeva|Veeva\s*CTMS|Veeva\s*Vault|Veeva\s*eTMF|Veeva\s*RTSM|Veeva\s*EDC|SiteVault|Veeva\s*CRM|Veeva\s*Clinical\s*Platform)\b",
    r"\b(?:Medidata|Medidata\s*Rave|Rave\s*EDC|Medidata\s*CTMS|Medidata\s*eTMF|Clinical\s*Data\s*Studio|Medidata\s*eConsent|Medidata\s*eCOA)\b",
    r"\b(?:Oracle\s*Clinical|Oracle\s*Clinical\s*One|Oracle\s*InForm|Oracle\s*CTMS|Oracle\s*Safety|Oracle\s*Health\s*Sciences|Oracle\s*Argus)\b",
    r"\b(?:IQVIA\s*RTSM|IQVIA\s*EDC|IQVIA\s*CTMS|IQVIA\s*eTMF|IQVIA\s*OCE|Orchestrated\s*Clinical\s*Trials|IQVIA\s*OneKey|Citeline|Trialtrove|Pharmaprojects)\b",
    r"\b(?:Clario|Signant\s*Health|Signant|Castor\s*EDC|Castor|OpenClinica|REDCap|Clinical\s*Conductor|Advarra|WCG|WIRB|Copernicus)\b",
    r"\b(?:Bioclinica|ERT|PHT|Exponent|Trial\s*Interactive|TransPerfect|Lionbridge|RWS|CSOFT|Welocalize)\b",
]

CENTRAL_LABS = [
    r"\b(?:Q2\s*Solutions|Q\s*Squared|Labcorp\s*Drug\s*Development|Labcorp\s*Central\s*Labs|Covance\s*Central\s*Labs)\b",
    r"\b(?:ICON\s*Central\s*Labs|PPD\s*Laboratories|Eurofins\s*Central\s*Lab|ACM\s*Global\s*Laboratories|BioAgilytix|Frontage\s*Labs|WuXi\s*Clinical)\b",
    r"\b(?:BARC\s*Global|MLM\s*Medical\s*Labs|Sonic\s*Clinical\s*Trials|Clinical\s*Reference\s*Laboratory|CRL)\b",
]

LAB_PRODUCT_PATTERNS = [
    r"\b[A-Z][a-z]+(?:amp|pure|zard)\s+(?:DNA|RNA|Genomic)?\s*(?:mini|midi|maxi|LS)?\s*(?:kit|purification)?\b",
    r"\b[A-Z][a-z]*(?:mix|lyser)(?:\.[A-Za-z]+)?\b",
    r"\b\d{4,5}[-]L\d{4,6}\b",
    r"\bP\d{3}[-]?\d{0,3}[A-Z]?\b",
    r"\b(?:RUO|IVD|CE[-]?IVD)\b",
    r"\b[a-z]+(?:MLPA|LPA|NER|PCR|DNA|RNA)\b",
]

ACRONYM_PATTERNS = [
    r"\b[A-Z]{2,5}[-]?[A-Z]{0,3}\s+(?:Select|Plus|Pro|Kit|System|Assay|Panel|Array)\b",
]

ACRONYM_ALLCAPS_RE = re.compile(r'\b[A-Z]{3,}\b')

SOFTWARE_PRODUCT_PATTERNS = [
    r"\b(?:Microsoft|Windows)\s+(?:Windows\s+)?(?:Server|Azure|Office|Teams|SharePoint|OneDrive|Dynamics|Exchange|SQL\s*Server|Visual\s*Studio|Power\s*BI|Outlook|Word|Excel|PowerPoint|Access|Publisher|OneNote|Project|Visio|Intune|Defender|Sentinel|Entra|Copilot|365|2012|2016|2019|2022|2025)(?:\s+(?:R2|Standard|Enterprise|Datacenter|Professional|Home|Pro|Ultimate|Education|Business|Premium|\d+(?:\.\d+)*))?\b",
    r"\b(?:Oracle|SAP|Salesforce|ServiceNow|Workday|Kronos|ADP|Concur|Ariba|SuccessFactors|Tableau|Snowflake|Databricks|Splunk|Elastic|MongoDB|Redis|PostgreSQL|MySQL|MariaDB|Teradata|Informatica|Talend|MicroStrategy|Qlik|Domo|Looker|Alteryx)\b",
    r"\b(?:VMware|Citrix|Red\s*Hat|SUSE|Canonical|Ubuntu|Debian|CentOS|Rocky\s*Linux|AlmaLinux|Fedora|openSUSE)(?:\s+[A-Za-z]+(?:\s+[A-Za-z0-9]+)*)?\b",
    r"\b(?:IBM|Dell|HP|HPE|Hewlett[-\s]?Packard|Cisco|Juniper|Arista|Palo\s*Alto|Fortinet|F5|Netscaler|Checkpoint|Zscaler|Crowdstrike|SentinelOne|Carbon\s*Black|Symantec|McAfee|Trend\s*Micro|Sophos|ESET|Kaspersky|Bitdefender|Avast|Norton|Malwarebytes)\b",
    r"\b(?:AWS|Amazon\s*Web\s*Services|Amazon|Google\s*Cloud|GCP|Google|Azure|IBM\s*Cloud|Alibaba\s*Cloud|Alibaba|DigitalOcean|Linode|Vultr|Heroku|Vercel|Netlify|Cloudflare|Akamai|Fastly)\b",
    r"\b(?:SpaceX|Tesla|Neuralink|Boring\s*Company|OpenAI|Anthropic|DeepMind|Meta|Facebook|Instagram|WhatsApp|TikTok|ByteDance|Twitter|X\s*Corp|Snapchat|Pinterest|LinkedIn|Reddit|Discord|Telegram|Signal)\b",
    r"\b(?:Netflix|Spotify|Disney|Hulu|HBO|Warner\s*Bros|Universal|Paramount|Sony\s*Pictures|MGM|Lionsgate|DreamWorks|Pixar|Lucasfilm|Marvel|DC\s*Comics|Activision|Blizzard|EA|Ubisoft|Epic\s*Games|Valve|Riot\s*Games|Rockstar|Bethesda|CD\s*Projekt)\b",
    r"\b(?:Uber|Lyft|Airbnb|Booking|Expedia|TripAdvisor|Yelp|DoorDash|Instacart|Grubhub|Postmates|Deliveroo|Just\s*Eat|Rappi|Glovo|iFood)\b",
    r"\b(?:PayPal|Stripe|Square|Block|Adyen|Klarna|Affirm|Afterpay|Venmo|Cash\s*App|Revolut|N26|Monzo|Chime|Robinhood|Coinbase|Binance|Kraken|FTX|Gemini)\b",
    r"\b(?:Kubernetes|Docker|Podman|OpenShift|Rancher|Tanzu|EKS|AKS|GKE|Helm|Terraform|Ansible|Puppet|Chef|SaltStack|Vagrant|Packer)\b",
    r"\b(?:Jenkins|GitLab|GitHub|Bitbucket|Azure\s*DevOps|CircleCI|Travis\s*CI|TeamCity|Bamboo|Octopus\s*Deploy|ArgoCD|Flux|Spinnaker)\b",
    r"\b(?:Jira|Confluence|Trello|Asana|Monday|Notion|Slack|Zoom|Webex|GoToMeeting|BlueJeans|RingCentral|Twilio|Vonage|Genesys|Five9|NICE|Avaya|Mitel)\b",
    r"\b(?:Adobe|Acrobat|Photoshop|Illustrator|InDesign|Premiere|After\s*Effects|XD|Figma|Sketch|InVision|Canva|Miro|Lucidchart|Draw\.io|Visio)\b",
    r"\b(?:AutoCAD|SolidWorks|CATIA|NX|Creo|Inventor|Revit|ArchiCAD|SketchUp|Rhino|Blender|Maya|3ds\s*Max|Cinema\s*4D|Houdini|ZBrush)\b",
    r"\b(?:NVIDIA|AMD|Intel|Qualcomm|Broadcom|Texas\s*Instruments|NXP|Infineon|STMicroelectronics|Microchip|Xilinx|Altera|Lattice)\b",
    r"\b(?:Apple|iPhone|iPad|MacBook|iMac|Mac\s*Pro|Mac\s*Mini|Apple\s*Watch|AirPods|HomePod|Apple\s*TV|macOS|iOS|iPadOS|watchOS|tvOS|Safari|Xcode|Swift|Objective-C)\b",
    r"\b(?:Dell|Lenovo|ASUS|Acer|HP|Hewlett[-\s]?Packard|Sony|Toshiba|Fujitsu|Panasonic|LG|Samsung|Huawei|Xiaomi|OPPO|Vivo|OnePlus|Motorola|Nokia|Ericsson|ZTE|HTC|BlackBerry|Palm)\b",
    r"\b(?:ThinkPad|ThinkCentre|ThinkStation|IdeaPad|IdeaCentre|Legion|Yoga|ROG|ZenBook|VivoBook|TUF|Strix|ProBook|EliteBook|ZBook|Latitude|Precision|OptiPlex|PowerEdge|Inspiron|XPS|Alienware|Vostro)\b",
    r"\b(?:PlayStation|Xbox|Nintendo\s+Switch|Steam\s*Deck|Oculus|Quest|HoloLens|Kindle|Fire\s*TV|Roku|Chromecast|Apple\s*TV|Sonos|Bose|JBL|Harman|Bang\s*&\s*Olufsen|Sennheiser|Audio[-\s]?Technica)\b",
    r"\b(?:Canon|Nikon|Sony|Fujifilm|Olympus|Panasonic|Leica|Hasselblad|GoPro|DJI|Garmin|Fitbit|Polar|Suunto|Wahoo|Zwift)\b",
    r"\b(?:SAP\s*S/4HANA|SAP\s*ECC|SAP\s*BW|SAP\s*HANA|SAP\s*Fiori|SAP\s*Ariba|SAP\s*Concur|SAP\s*SuccessFactors|SAP\s*Hybris|SAP\s*C/4HANA)\b",
    r"\b(?:Epic|Cerner|MEDITECH|Allscripts|athenahealth|eClinicalWorks|NextGen|Greenway|Aprima|DrChrono|Practice\s*Fusion|Kareo|CureMD)\b",
    r"\bVelocity(?:\s+\d+(?:\.\d+)*)?\s+GRID(?:\s+Server)?\b",
    r"\b(?:Gmail|Hotmail|Outlook\.com|Yahoo\s*Mail|Yahoo|AOL|ProtonMail|Proton\s*Mail|Zoho\s*Mail|Zoho|iCloud|Mail\.ru|Yandex\s*Mail|Yandex|GMX|Tutanota|FastMail|Mailfence|Runbox|Posteo|StartMail|Hushmail|Comcast|Comcast\.net|Xfinity|Verizon|AT&T|T-Mobile|Vodafone|Movistar|Orange|Telefonica|Telef[oó]nica)\b",
    r"\b(?:Aliyun|Alibaba\s*Mail|QQ\s*Mail|NetEase|163\.com|126\.com|Sina|Sohu|Baidu|Tencent|WeChat|Weibo|Douyin|Kuaishou|Bilibili|JD\.com|Pinduoduo|Meituan|Didi|ByteDance|Line|KakaoTalk|Kakao|Naver|Daum)\b",
    r"\b(?:Outlook|Teams|OneDrive|OneNote|SharePoint|Skype|Bing|Cortana|Edge|Internet\s*Explorer|Firefox|Chrome|Chromium|Opera|Brave|Vivaldi|Tor\s*Browser|DuckDuckGo|Ecosia)\b",
    r"\b(?:Dropbox|Box|WeTransfer|MediaFire|Mega|pCloud|Tresorit|Sync\.com|SpiderOak|Backblaze|Carbonite|CrashPlan|IDrive|Wasabi)\b",
    r"\b(?:Carestream|Kodak|Agfa|Fujifilm|Siemens\s*Healthineers|Siemens|Philips|GE\s*Healthcare|Medtronic|Stryker|Zimmer\s*Biomet|Becton\s*Dickinson|Baxter|Edwards\s*Lifesciences|Abbott|Boston\s*Scientific|Danaher|Hologic|Intuitive\s*Surgical|ResMed|Varian|Elekta)\b",
]

# Common instruction verbs to exclude from product name detection
INSTRUCTION_VERBS = {
    'install', 'click', 'open', 'select', 'choose', 'press', 'enter', 'type',
    'go', 'run', 'start', 'stop', 'close', 'save', 'load', 'download', 'upload',
    'create', 'delete', 'remove', 'add', 'edit', 'update', 'view', 'see',
    'check', 'find', 'search', 'browse', 'navigate', 'access', 'use', 'try',
    'test', 'verify', 'confirm', 'accept', 'decline', 'cancel', 'submit',
    'send', 'receive', 'copy', 'paste', 'cut', 'move', 'drag', 'drop',
    'configure', 'setup', 'enable', 'disable', 'activate', 'deactivate',
    'instalar', 'abrir', 'seleccionar', 'elegir', 'pulsar', 'escribir',
    'ejecutar', 'iniciar', 'parar', 'cerrar', 'guardar', 'cargar', 'descargar',
    'crear', 'eliminar', 'borrar', 'añadir', 'editar', 'actualizar', 'ver',
    'comprobar', 'buscar', 'navegar', 'acceder', 'usar', 'probar',
    'verificar', 'confirmar', 'aceptar', 'rechazar', 'cancelar', 'enviar',
}

URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z]{2,})+(?:/[^\s]*)?\b",
]

CLINICAL_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?clinicaltrials\.gov/(?:ct2/show/|study/)?NCT\d{8}\b",
    r"(?:https?://)?(?:www\.)?eudract\.ema\.europa\.eu[^\s]*\b",
    r"(?:https?://)?(?:www\.)?euclinicaltrials\.eu[^\s]*\b",
    r"(?:https?://)?(?:www\.)?who\.int/(?:clinical-?trials|ictrp)[^\s]*\b",
    r"(?:https?://)?(?:www\.)?isrctn\.com/ISRCTN\d{8}\b",
    r"(?:https?://)?jrct\.niph\.go\.jp[^\s]*\b",
    r"(?:https?://)?ctri\.nic\.in[^\s]*\b",
    r"(?:https?://)?(?:www\.)?anzctr\.org\.au[^\s]*\b",
    r"(?:https?://)?drks\.de[^\s]*\b",
    r"(?:https?://)?(?:www\.)?chictr\.org\.cn[^\s]*\b",
    r"\bclinicaltrials\.gov\s*/?\s*(?:ct2/show/|study/)?NCT\d{8}\b",
    r"\b(?:see|visit|refer\s+to|available\s+at)?\s*(?:https?://)?clinicaltrials\.gov[^\s]*\b",
]

ADDRESS_PATTERNS = [
    r"\b\d{1,5}\s+[A-Z][a-zÀ-ÿ]+(?:\s+[A-Z][a-zÀ-ÿ]+)*\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Court|Ct\.?|Place|Pl\.?|Parkway|Pkwy\.?|Highway|Hwy\.?)\b",
    r"\b\d{1,5}\s+[A-Z][a-zÀ-ÿ]+(?:straat|weg|laan|plein|gracht|kade|singel|dijk|straße|stra[ßs]e|platz|allee)\b",
    r"\b\d{4,5}\s*[A-Z]{2}\b,?\s*[A-ZÀ-ÿ][a-zÀ-ÿ]+",
    r"\b[A-Z][a-zÀ-ÿ]+\s+\d+[-/]?\d*\s*,\s*\d{4,5}\s*[A-Z]?[A-Z]?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+\b",
    r"\b[A-Z]{1,2}\d{1,2}\s*\d[A-Z]{2}\b",
    r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b",
    r"\b(?:Building|Bldg|Block|Tower|Floor|Room|Office)\s*[#:]?\s*[A-Z0-9]+\s*,\s*\d{1,5}\s+[A-Za-z]+\b",
]

INVESTIGATOR_PATTERNS = [
    r"\b(?:Dr|Prof|Professor|Doctor)\.?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
    r"\b[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2},?\s*(?:MD|M\.D\.|PhD|Ph\.D\.|PharmD|Pharm\.D\.|DO|D\.O\.|RN|R\.N\.|NP|PA|MBBS|FRCP|FACP|FACS)\b",
    r"\b(?:Principal\s+Investigator|Sub-?Investigator|Study\s+Coordinator|Site\s+Director|Medical\s+Monitor|Study\s+Physician)[\s:]+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
    r"\b(?:PI|Co-?PI|SI)[\s:]+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
]

CLINICAL_DATE_PATTERNS = [
    r"\b[Qq][1-4]\s*[-/]?\s*(?:20[1-3]\d|FY\s*20[1-3]\d)\b",
    r"\b(?:FY|CY)\s*20[1-3]\d\b",
    r"\b(?:H1|H2|1H|2H)\s*[-/]?\s*20[1-3]\d\b",
    r"\b(?:Visit|Day|Week|Month|Year)\s*[-#:]?\s*\d{1,3}\b",
    r"\b(?:V|D|W|M)\d{1,3}\b(?=\s|$|[,;.])",
    r"\b(?:Screening|End\s*of\s*(?:Study|Treatment|Trial)|Follow[\s-]?up|Randomization|Enrollment)\s*(?:Visit)?\b",
    r"\bBaseline\s+(?:Visit|Date|Period|Assessment|Evaluation|Examination|Value|Measurement)\b",
    r"\b(?:At|From|Since|After|Before|Pre|Post)[\s-]?Baseline\b",
    r"\b(?:Study|Protocol|Amendment)\s*(?:Start|End|Initiation|Completion|Termination)\s*(?:Date)?[\s:]+\d{1,2}[-/]\d{1,2}[-/]20[1-3]\d\b",
]

LOT_BATCH_PATTERNS = [
    r"\b(?:LOT|Lot|BATCH|Batch)[-#:\s]*[A-Z0-9]{2,}[-/]?[A-Z0-9]{2,}[-/]?[A-Z0-9]*\b",
    r"\b(?:Kit|Vial|Bottle|Ampule|Ampoule)[-#:\s]*(?:ID|No|Number)?[-#:\s]*[A-Z0-9]{4,}\b",
    r"\bSample\s+(?:ID|No|Number)[-#:\s]*[A-Z0-9]{4,}\b",
    r"\b(?:Exp(?:iry)?|MFG|Manufacturing)[-:\s]*(?:Date)?[-:\s]*\d{2}[-/]\d{2}[-/]?\d{2,4}\b",
    r"\b[A-Z]{2,3}[-]?\d{4,8}[-]?[A-Z]?\d{0,4}\b(?=\s+(?:lot|batch|expir))",
]

SITE_CODE_PATTERNS = [
    r"\b\d{3}[-]?[A-Z]{2}[-]?[A-ZÀ-ÿ][a-zÀ-ÿ]+\b",
    r"\b(?:Site|Centro|Centre|Center|Sitio)[-#:\s]*\d{2,4}[-]?[A-Z]{0,3}\b",
    r"\b[A-Z]{2,3}[-]?\d{3,4}[-]?(?:Site|Centro|Centre)?\b",
    r"\bS\d{3,4}[-]?[A-Z]{0,2}\b",
    r"\b(?:Investigator|Inv)[-#:\s]*(?:Site|ID)?[-#:\s]*\d{3,5}\b",
    r"\b\d{4}[-][A-Z]{2,3}[-]\d{3}\b",
    r"\b\d{4}[-]\d{3,4}[-]\d{2,4}\b",
]

IRB_ETHICS_PATTERNS = [
    r"\b(?:IRB|CEIC|CEISH|CEIM|CEI|EC|REB|HREC|IEC|DSMB|DMC)[-#:\s]*\d{4,}\b",
    r"\b(?:IRB|Ethics|Ethical)[-\s]*(?:Committee|Board|Approval|Review)?[-#:\s]*(?:No|Number|ID)?[-#:\s]*[A-Z0-9]{2,}[-/]?\d{2,}\b",
    r"\b(?:Protocol|Study)[-\s]*(?:Approval|Authorization)[-#:\s]*[A-Z0-9]{2,}[-/]?\d{4,}\b",
    r"\b(?:Comité\s+(?:de\s+)?[ÉE]tica|Ethics\s+Committee|Institutional\s+Review\s+Board)\s+(?:Approval|Reference)?[-#:\s]*[A-Z0-9/-]+\b",
    r"\b(?:FDA|EMA|PMDA|TGA|Health\s+Canada|ANVISA|NMPA|MHRA)[-\s]*(?:Approval|IND|NDA|BLA|MAA)?[-#:\s]*\d{4,}\b",
]

AGE_RANGE_PATTERNS = [
    r"\b(?:aged?|ages?)\s*(?:\d{1,3}\s*[-–to]+\s*\d{1,3}|\d{1,3}\s*(?:years?|y\.?o\.?|yo))\b",
    r"\b[≥≤><]\s*\d{1,3}\s*(?:years?(?:\s+(?:of\s+)?age)?|y\.?o\.?)\b",
    r"\b(?:between|from)\s+\d{1,3}\s+(?:and|to)\s+\d{1,3}\s+(?:years?(?:\s+(?:of\s+)?age)?)\b",
    r"\b\d{1,3}\s*[-–]\s*\d{1,3}\s*(?:years?(?:\s+(?:of\s+)?age)?|y\.?o\.?)\b",
    r"\b(?:pediatric|paediatric|adult|elderly|geriatric)\s+(?:patients?|subjects?|population|cohort)\s*\(?\d{1,3}\s*[-–to]+\s*\d{1,3}(?:\s*years?)?\)?\b",
    r"\b(?:inclusion|exclusion|eligibility)[-:\s]*.*?(?:age|años|âge)\s*[≥≤><]?\s*\d{1,3}\b",
]


COUNTRY_NATIONALITY_PATTERNS = []

STUDY_NAME_PATTERNS = [
    r"\b(?:KEYNOTE|CHECKMATE|JAVELIN|IMPOWER|HIMALAYA|TOPAZ|DESTINY|EMBRACE|MONALEESA|PALOMA|MONARCH|OLYMPIA|PEARL|PRIMA|PROFOUND|TRITON|TALAPRO|MAGNITUDE|PROPEL|ENZAMET|TITAN|ARASENS|SPARTAN|PROSPER|GALAHAD|VISION|PSMA|TAILOR|ACORN|ARROW|BEACON|CASCADE|ELEVATE|FALCON|GEMINI|HORIZON|INFINITY|JUPITER|LOTUS|NAUTILUS|ORION|PIONEER|QUEST|RADIANT|STELLAR|TRINITY|ULTRA|VERTEX|WISDOM|XENON|ZENITH)[-]?\d{0,4}\b",
    r"\b(?:SOLO|NOVA|ARIEL|POLO|DELTA)[-]\d{1,4}\b",
    r"\b(?:Study|Trial|Protocol)\s+[A-Z]{2,5}[-]?\d{3,5}(?:[-][A-Z]{1,3})?\b",
    r"\b[A-Z]{2,4}[-]?\d{3,5}[-]?(?:Study|Trial)\b",
    r"\b(?:Phase\s+)?[IViv]{1,3}[ab]?\s+(?:Study|Trial)\s+[A-Z0-9]{2,8}\b",
]

RANDOMIZATION_PATTERNS = [
    r"\b(?:Randomization|Randomisation|RANDO|RAND)[-#:\s]*(?:No|Number|ID|Code)?[-#:\s]*[A-Z0-9]{2,}[-]?\d{4,}\b",
    r"\b(?:IVRS|IWRS|IRT|IxRS)[-#:\s]*(?:No|Number|ID|Code)?[-#:\s]*[A-Z0-9]{4,}\b",
    r"\b(?:Subject|Patient|Screening)[-\s]*(?:Randomization|Randomisation)[-#:\s]*[A-Z0-9]{2,}[-]?\d{3,}\b",
    r"\b(?:Treatment|Arm|Group)[-\s]*(?:Assignment|Allocation)[-#:\s]*[A-Z0-9]{2,}\b",
    r"\b(?:Kit|Drug|Medication)[-\s]*(?:Number|No|ID|Code)[-#:\s]*[A-Z0-9]{4,}\b",
    r"\b(?:Blinded|Unblinded)[-\s]*(?:Code|ID|Number)[-#:\s]*[A-Z0-9]{4,}\b",
]

MEDICAL_DEVICE_PATTERNS = [
    r"\b(?:Medtronic|Boston\s*Scientific|Abbott|Edwards\s*Lifesciences|Stryker|Zimmer\s*Biomet|Johnson\s*&\s*Johnson|Siemens\s*Healthineers|Philips|GE\s*Healthcare|BD|Becton\s*Dickinson|Baxter|Fresenius|B\.?\s*Braun|Smith\s*&\s*Nephew|Intuitive\s*Surgical|Dexcom|Insulet|Tandem|Terumo|Olympus|Cook\s*Medical|Hologic)\b",
    r"\b(?:DaVinci|da\s*Vinci|Optima|Signa|Ingenia|Artis|Somatom|Navigator|Libre|Guardian|Enlite|G6|G7|OmniPod|Minimed|Accu-Chek|OneTouch|Contour|FreeStyle)\b",
    r"\b(?:Stent|Pacemaker|Defibrillator|ICD|CRT|Catheter|Valve|Prosthesis|Implant|Pump|Monitor|Sensor|Electrode|Lead|Graft|Mesh|Scaffold|Coil|Filter|Balloon|Shunt|Port|Reservoir)\s+[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)?\b",
    r"\b[A-Z][a-zA-Z]*(?:Stent|Valve|Cath|Pump|Lead|Graft|Mesh|Coil|Flow|Guard|Seal|Fix|Flex|Plus|Pro|Ultra|Max|Elite|Prime|Neo|Next|One|360|3D)\b",
    r"\b(?:CE[-\s]?marked|510\(k\)|PMA|De\s*Novo|Class\s+[IViv]{1,3})\s+(?:device|product|system)\b",
]

INTERNATIONAL_PHONE_PATTERNS = [
    r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{0,4}\b",
    r"\b00\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b",
    r"\b\(\d{2,4}\)\s*\d{3,4}[-.\s]?\d{3,4}\b",
    r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
    r"\b\d{4}[-.\s]\d{3}[-.\s]\d{3}\b",
    r"\b\d{2}[-.\s]\d{4}[-.\s]\d{4}\b",
    r"\b(?:Tel|Phone|Fax|Mobile|Cell)[-:\s]*[+]?\d[\d\s\-().]{7,18}\b",
    r"\b\d{2}\s+\d{3}\s+\d{3}\b",
    r"\b\d{3}\s+\d{3}\s+\d{3}\b",
    r"\b\d{3}\s+\d{2}\s+\d{2}\s+\d{2}\b",
    r"\b9\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b",
    r"\b[67]\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b",
]

CORPORATE_EMAIL_PATTERNS = [
    r"\b[A-Za-z0-9._%+-]+@(?:pfizer|novartis|roche|sanofi|merck|msd|astrazeneca|gsk|glaxosmithkline|abbvie|bms|bristol-?myers|lilly|amgen|gilead|bayer|novonordisk|novo-nordisk|takeda|boehringer|biogen|regeneron|moderna|biontech|teva|astellas|eisai|vertex|alexion|iqvia|ppd|icon|syneos|parexel|covance|labcorp|medpace|fortrea|wuxi|pra-health|quintiles)\.com\b",
    r"\b[A-Za-z0-9._%+-]+@(?:veeva|medidata|oracle|citeline|clario|signant|castor|advarra|wcg|transperfect|lionbridge|rws|csoft|welocalize)\.com\b",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:pharma|clinical|medical|health|research|trials?|study|bio|med)\.[A-Za-z]{2,}\b",
]

POSTAL_CODE_PATTERNS = [
    r"\b\d{5}(?:[-\s]?\d{4})?\b(?=\s*(?:USA?|United\s+States|[A-Z]{2}\s|,))",
    r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b",
    r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b",
    r"\b\d{3}[-\s]?\d{4}\b(?=\s*(?:Japan|JP|Tokyo|Osaka))",
    r"\b\d{4}\s*[A-Z]{2}\b",
    r"\b\d{5}\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+\b(?=\s*(?:Germany|France|Spain|Italy|DE|FR|ES|IT))",
    r"\b(?:CP|C\.P\.|Código\s+Postal|Postcode|ZIP|PLZ)[-:\s]*\d{4,6}[-\s]?[A-Z]{0,2}\b",
]

DOB_PATTERNS = [
    r"\b(?:DOB|D\.O\.B\.|Date\s+of\s+Birth|Birth\s*Date|Fecha\s+de\s+Nacimiento|Geburtsdatum|Date\s+de\s+Naissance)[-:\s]*\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b",
    r"\b(?:DOB|D\.O\.B\.|Date\s+of\s+Birth|Birth\s*Date)[-:\s]*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]*\d{1,2}[-,.\s]*\d{2,4}\b",
    r"\b(?:Born|Nacido|Né|Geboren)[-:\s]*(?:on\s+)?(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]*\d{1,2}[-,.\s]*\d{2,4})\b",
    r"\b(?:Age|Edad|Âge|Alter)[-:\s]*\d{1,3}\s*(?:years?|años|ans|Jahre)?\s*(?:old)?\b",
]

XLIFF_NS = {
    "xliff": "urn:oasis:names:tc:xliff:document:1.2",
    "mq": "MQXliff"
}

INLINE_TAG_NAMES = {"ph", "bpt", "ept", "it", "bx", "ex", "x", "g", "mrk", "sub"}

CRITICAL_PII_PATTERNS = [
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}",
    r"(?:https?://)[^\s]+",
    r"\bNCT\d{8}\b",
    r"\b\d{4}-\d{6}-\d{2}\b",
]

SAFE_REGEX_PATTERNS = {
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "NCT_ID": r"\bNCT\d{8}\b",
    "ISRCTN_ID": r"\bISRCTN\d{8}\b",
    "JRCT_ID": r"\bjRCT[a-zA-Z]?\d{7,10}\b",
    "CTRI_ID": r"\bCTRI[/\-]\d{4}[/\-]\d{2,3}[/\-]\d{5,6}\b",
    "ANZCTR_ID": r"\bACTRN\d{14}\b",
    "CHICTR_ID": r"\bChiCTR[-]?(?:[A-Z]{2,4}[-]?)?\d{7,10}\b",
    "DRKS_ID": r"\bDRKS\d{8}\b",
    "IRCT_ID": r"\bIRCT\d{14,}\b",
    "UMIN_ID": r"\bUMIN\d{9}\b",
    "KCT_ID": r"\bKCT\d{7}\b",
    "EU_CT_ID": r"\bEU[-\s]?CT\s*\d{4}[-\s]?\d{4,6}[-\s]?\d{2}[-\s]?\d{2}\b",
    "NIF_CIF_ES": r"\b(?:NIF|CIF|DNI|NIE)[\s:.-]*[A-Z]?\d{7,8}[-]?[A-Z]?\b",
    "DNI_STANDALONE": r"\b\d{8}[-]?[A-Z]\b",
    "NIF_STANDALONE": r"\b[A-Z]\d{7,8}[-]?[A-Z]?\b",
    "SSN_US": r"\b(?:SSN|Social\s+Security)[\s:.-]*\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    "SSN_US_STANDALONE": r"\b\d{3}[-]\d{2}[-]\d{4}\b",
    "EIN_US": r"\b(?:EIN|Tax\s+ID)[\s:.-]*\d{2}[-]?\d{7}\b",
    "NINO_UK": r"\b(?:NINO|National\s+Insurance)[\s:.-]*[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
    "NINO_UK_STANDALONE": r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
    "NHS_UK": r"\b(?:NHS)[\s:.-]*\d{3}\s?\d{3}\s?\d{4}\b",
    "SECU_FR": r"\b(?:Sécurité\s+Sociale|INSEE|Numéro\s+SS|N°?\s*SS)[\s:.-]*[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b",
    "SECU_FR_STANDALONE": r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b",
    "CODICE_FISCALE_IT": r"\b(?:Codice\s+Fiscale|CF)[\s:.-]*[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
    "CODICE_FISCALE_IT_STANDALONE": r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
    "PARTITA_IVA_IT": r"\b(?:P\.?\s*IVA|Partita\s+IVA)[\s:.-]*(?:IT)?\d{11}\b",
    "NIF_PT": r"\b(?:NIF|NIPC|Contribuinte)[\s:.-]*[123568]\d{8}\b",
    "CC_PT": r"\b(?:Cartão\s+de\s+Cidadão|CC)[\s:.-]*\d{8}\s?\d\s?[A-Z]{2}\d\b",
    "BSN_NL": r"\b(?:BSN|Burgerservicenummer)[\s:.-]*\d{9}\b",
    "NISS_BE": r"\b(?:NISS|Rijksregisternummer|Registre\s+National)[\s:.-]*\d{2}[\.\s]?\d{2}[\.\s]?\d{2}[-\s]?\d{3}[-\.\s]?\d{2}\b",
    "AHV_CH": r"\b(?:AHV|AVS|OASI)[\s:.-]*756[\.\s]?\d{4}[\.\s]?\d{4}[\.\s]?\d{2}\b",
    "CPF_BR": r"\b(?:CPF)[\s:.-]*\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[-\s]?\d{2}\b",
    "CNPJ_BR": r"\b(?:CNPJ)[\s:.-]*\d{2}[\.\s]?\d{3}[\.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}\b",
    "CURP_MX": r"\b(?:CURP)[\s:.-]*[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]{2}\b",
    "PPS_IE": r"\b(?:PPS|PPSN)[\s:.-]*\d{7}[A-Z]{1,2}\b",
    "SHENFENZHENG_CN": r"(?:身份证(?:号(?:码)?)?|居民身份证)[\s:：]*[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]",
    "SHENFENZHENG_CN_STANDALONE": r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)",
    "MY_NUMBER_JP": r"(?:マイナンバー|個人番号)[\s:：]*\d{4}\s?\d{4}\s?\d{4}",
    "MULTI_PART_CODE": r"\b[A-Z]{2,5}[-][A-Z]{2,5}[-][A-Z0-9]{2,8}(?:[-][A-Z0-9]{1,5})?\b",
    "MIXED_ALPHANUMERIC_CODE": r"\b[A-Z]{2,6}[-][A-Z0-9]{2,10}[-][A-Z0-9]{2,10}(?:[-][A-Z0-9]{1,6})?\b",
    "STRUCTURED_ID": r"\b[A-Z]{2,6}[-_/]\d{2,8}\b",
    "LONG_NUMBER_ID": r"\b\d{3,}(?:[-./]\d{2,})+\b|\b\d{6,}[A-Za-z]*\b",
    "IBAN_CODE": r"\b[A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{0,4}\b",
    "SS_ES": r"\b\d{2}[-/]\d{7,8}[-/]\d{2}\b",
    "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "URL_HTTPS": r"(?:https?://)[^\s]+",
    "URL_DOMAIN": r"\b[A-Za-z0-9][-A-Za-z0-9]*(?:\.[A-Za-z0-9][-A-Za-z0-9]*)*\.(?:gov|edu|org|com|net|int|eu|es|uk|de|fr|it|pt|nl|be|at|ch|co|info|mil|ai)(?:/[^\s,.)]*)?",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "TRADEMARK_NAME": r"\b[A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\-]*(?:\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\-]*){0,3}\s*[®™]",
    "COPYRIGHT_NAME": r"[©]\s*(?:\d{4}\s+)?[A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\-]+(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\-]+){0,3}(?!\w)",
}

SAFE_REGEX_PHONE_PATTERNS = [
    r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{0,4}\b",
    r"\b00\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b",
    r"\(\d{2,4}\)\s*\d{3,4}[-.\s]?\d{3,4}\b",
    r"\b(?:Tel|Phone|Fax|Mobile|Cell|Tfno|Teléfono|Telefon|Telefono|Téléphone|Telefoon|Cellulare|Portable|Handy|Mobiel)[-:\s]*[+]?\d[\d\s\-().]{7,18}\b",
    r"\b9\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b",
    r"\b[67]\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b",
    r"\b\d{2,4}[\s-]\d{3,4}(?:[\s-]\d{2,4}){1,}\b",
]

SAFE_REGEX_ADDRESS_PATTERNS = [
    r"\b\d{1,5}\s+(?:[A-Z][a-zÀ-ÿ]+|\d{1,3}(?:st|nd|rd|th))(?:\s+(?:[A-Z][a-zÀ-ÿ]+|\d{1,3}(?:st|nd|rd|th)))*\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Court|Ct\.?|Place|Pl\.?|Parkway|Pkwy\.?|Highway|Hwy\.?)\b",
    r"\b\d{1,5}\s+[A-Z][a-zÀ-ÿ]+(?:straat|weg|laan|plein|gracht|kade|singel|dijk|straße|stra[ßs]e|platz|allee)\b",
    r"\b(?:Building|Bldg|Block|Tower|Floor|Room|Office|Edificio|Étage|Piano|Gebäude|Verdieping)\s*[#:]?\s*[A-Z0-9]+\s*,\s*\d{1,5}\s+[A-Za-z]+\b",
    r"\b(?:[Cc]alle|[Aa]venida|[Aa]vda|[Pp]aseo|[Pp]laza|[Cc]amino|[Cc]arretera|[Rr]onda|[Tt]ravesía|[Gg]lorieta|[Cc]/|[Cc]\.\s|[Aa]v\.)\s*(?:(?:de|del|de\s+la|de\s+el|de\s+los|de\s+las)\s+)?[A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+){0,3}\s*(?:[,]\s*)?(?:(?:nº?\s*|#\s*)?\d{1,4})?\b",
    r"\b(?:[Dd]irección|[Aa]ddress|[Aa]dresse|[Ii]ndirizzo|[Aa]dres)[-:\s]+[A-ZÀ-ÿa-zÀ-ÿ].{5,60}(?:\d{4,5}\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+)\b",
    r"\b(?:[Rr]ue|[Bb]oulevard|[Aa]venue|[Pp]lace|[Cc]hemin|[Ii]mpasse)\s+(?:de\s+la\s+|du\s+|des\s+|de\s+|d')?[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+){0,3}\s*(?:[,]\s*)?(?:\d{1,4})?\b",
    r"\b(?:[Vv]ia|[Vv]iale|[Pp]iazza|[Cc]orso|[Ll]argo|[Vv]icolo)\s+(?:della?\s+|delle?\s+|degli?\s+|dei?\s+)?[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+){0,3}\s*(?:[,]\s*)?(?:\d{1,4})?\b",
    r"\b(?:[Rr]ua|[Aa]venida|[Pp]raça|[Tt]ravessa|[Ll]argo)\s+(?:da\s+|do\s+|das\s+|dos\s+|de\s+)?[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+){0,3}\s*(?:[,]\s*)?(?:(?:nº?\s*|#\s*)?\d{1,4})?\b",
]

SAFE_REGEX_POSTAL_PATTERNS = [
    r"\b(?:CP|C\.P\.|Código\s+Postal|Postcode|ZIP|PLZ|CAP|Code\s+Postal|Postcode|Postbus)[-:\s]*\d{4,6}[-\s]?[A-Z]{0,2}\b",
    r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b",
    r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b",
    r"\b\d{4}\s?[A-Z]{2}\b",
    r"\b\d{5}\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s*,\s*|\s+)(?:Spain|España|Germany|Deutschland|France|Francia|Italia|Italy|Portugal|Netherlands|Nederland|Belgium|Belgique|België|Switzerland|Suisse|Schweiz|Svizzera|Brazil|Brasil|Mexico|México|Ireland|Irlanda)\b",
    r",\s*\d{5}\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+\b",
]

SAFE_REGEX_TITLED_NAME_PATTERNS = [
    r"\b(?:Dr|Dra|Prof|Professor|Doctor|Doctora|Dott|Dott\.ssa|Professore|Professoressa|Docteur|Professeur)\.?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,3}\b",
    r"\b(?:Mr|Mrs|Ms|Miss|Sir|Lady|Lord)\.?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,3}\b",
    r"\b(?:Don|Doña|Sr|Sra|Srta|Lic|Ing|Arq|Abog|Mtro|Mtra)\.?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,3}\b",
    r"\b(?:Herr|Frau|Monsieur|Madame|Mme|Mlle|Sig|Sig\.ra|Dhr|Mevr|Mevrouw|Meneer)\.?\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,3}\b",
    r"\b[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2},?\s*(?:MD|M\.D\.|PhD|Ph\.D\.|PharmD|Pharm\.D\.|DO|D\.O\.|RN|R\.N\.|NP|PA|MBBS|FRCP|FACP|FACS|DDS|DMD|OD|DPM|DC)\b",
    r"\b(?:Principal\s+Investigator|Sub-?[Ii]nvestigator|Study\s+Coordinator|Site\s+Director|Medical\s+Monitor|Study\s+Physician|Investigador\s+Principal|Investigateur\s+Principal|Hauptprüfer|Prüfarzt|Ricercatore\s+Principale)[\s:]+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
    r"\b(?:PI|Co-?PI|SI)[\s:]+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
]

SAFE_REGEX_DOB_PATTERNS = [
    r"\b(?:DOB|D\.O\.B\.|Date\s+of\s+Birth|Birth\s*Date|Fecha\s+de\s+Nacimiento|Geburtsdatum|Date\s+de\s+Naissance|Data\s+di\s+Nascita|Geboortedatum|Data\s+de\s+Nascimento)[-:\s]*\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b",
    r"\b(?:DOB|D\.O\.B\.|Date\s+of\s+Birth|Birth\s*Date)[-:\s]*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]*\d{1,2}[-,.\s]*\d{2,4}\b",
    r"\b(?:Born|Nacido|Nacida|Né|Née|Geboren|Nato|Nata|Nascido|Nascida)[-:\s]*(?:on\s+|el\s+|le\s+|il\s+|am\s+|em\s+)?(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]*\d{1,2}[-,.\s]*\d{2,4})\b",
    r"(?:出生日期|生年月日|生日)[\s:：]*\d{4}[年/\-\.]\d{1,2}[月/\-\.]\d{1,2}[日]?",
    r"\d{4}年\d{1,2}月\d{1,2}日生(?:まれ)?",
]

SAFE_REGEX_CJK_TITLED_NAME_PATTERNS = [
    r"[\u4e00-\u9fff]{1,4}(?:医生|醫生|大夫|主任|教授|博士|院士|先生|女士|小姐)",
    r"(?:医生|醫生|大夫|主任|教授|博士|院士)[\s:：]*[\u4e00-\u9fff]{2,4}",
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{1,5}(?:先生|様|氏|さん|博士|教授|医師)",
    r"(?:医師|博士|教授)[\s:：]*[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,5}",
]

SAFE_REGEX_CJK_ADDRESS_PATTERNS = [
    r"〒\d{3}[-ー]\d{4}",
    r"(?:東京都|北海道|(?:大阪|京都)府|.{2,3}県).{1,6}[市区町村].{0,10}(?:\d{1,4}[-ー]\d{1,4}(?:[-ー]\d{1,4})?|[一二三四五六七八九十]+丁目)",
    r"[\u4e00-\u9fff]{2,6}(?:省|市|区|县|镇|村|路|街|道|巷|弄|号|幢|栋|室|楼)\s*(?:[\u4e00-\u9fff]*(?:省|市|区|县|镇|村|路|街|道|巷|弄|号|幢|栋|室|楼)\s*){1,5}\d{0,5}",
    r"(?:住所|地址)[\s:：]*[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\d\-ー]{5,}",
]

SAFE_REGEX_CJK_PHONE_PATTERNS = [
    r"(?:电话|電話|手机|手機|携帯|連絡先|联系电话)[\s:：]*[+＋]?\d[\d\s\-ー().（）]{7,18}",
]

# ============================================================================
# PERSON NAME DETECTION - Structural detection with list validation
# ============================================================================




# ---------------------------------------------------------------------------
# Proper Names layer (rule-based, no NLP): multilingual first/last name lists,
# hospital/institution patterns and context guards. Restored from the former
# Proper Names layer minus every spaCy/NER-dependent part.
# ---------------------------------------------------------------------------
HOSPITAL_PATTERNS = [
    r"\b(?:Hospital|Hosp\.?)\s+(?:Universitario|University|General|Regional|Central|Municipal|Nacional|National|Metropolitan|Memorial|Community|Children'?s|Infantil|Pedi[aá]trico|Cl[ií]nico|Teaching)\s+(?:de\s+|del\s+)?[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,3}\b",
    r"\b[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\s+(?:Hospital|Medical\s+Center|Clinic|Cl[ií]nica|Krankenhaus|Klinik|Hôpital|Ospedale|Ziekenhuis|Sjukhus|Sykehus)\b",
    r"\b(?:Medical\s+Center|Centro\s+M[eé]dico|Centre\s+M[eé]dical|Medizinisches\s+Zentrum)\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
    r"\b(?:Cl[ií]nica|Clinic|Klinik)\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\b",
    r"\b(?:University|Universidad|Universit[äa]t|Universit[eé])\s+(?:of\s+)?[A-ZÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+){0,2}\s+(?:Hospital|Medical\s+Center|School\s+of\s+Medicine|Faculty\s+of\s+Medicine)\b",
    r"\b(?:NHS|VA|Veterans\s+Affairs|Kaiser|Mayo|Cleveland|Johns\s+Hopkins|Mass\s+General|MGH|Cedars[- ]Sinai|Mount\s+Sinai|NYU\s+Langone|Stanford\s+Health|UCSF|UCLA\s+Health)\b",
    r"\b(?:Charit[eé]|AP-HP|Karolinska|Huddinge|Sahlgrenska|Rigshospitalet|Erasmus\s+MC|UMC\s+Utrecht|LMU\s+Klinikum|Heidelberg\s+University\s+Hospital)\b",
    r"\b(?:Institut|Institute|Centro|Centre|Center)\s+(?:of\s+|de\s+|für\s+)?(?:Oncology|Oncolog[ií]a|Cancer|Cardiology|Cardiolog[ií]a|Neurology|Neurolog[ií]a|Research|Investigaci[oó]n)\s*[A-ZÀ-ÿ]?[a-zÀ-ÿ]*\b",
]

ALL_FIRST_NAMES = {
    # Spanish (50)
    "maría", "juan", "josé", "ana", "carlos", "luis", "pedro", "antonio",
    "francisco", "manuel", "david", "javier", "miguel", "ángel", "rafael",
    "fernando", "daniel", "pablo", "jorge", "alberto", "sergio", "alejandro",
    "rosa", "carmen", "laura", "marta", "elena", "lucía", "sofía", "paula",
    "isabel", "teresa", "cristina", "patricia", "beatriz", "irene", "andrea",
    "ricardo", "roberto", "eduardo", "diego", "andrés", "gabriel", "raúl",
    "adrián", "héctor", "arturo", "ignacio", "tomás", "ramón", "emilio",
    "gonzalo", "jaime", "nuria", "álvaro", "rubén", "víctor", "iván",
    "paz", "luz", "consuelo", "dolores", "pilar", "mercedes", "soledad",
    "esperanza", "amparo", "nieves", "remedios", "milagros", "rocío",
    "aurora", "blanca", "estrella", "victoria", "mar", "inmaculada",
    "guillermo", "enrique", "alfredo", "rodrigo", "nicolás", "mateo",
    # English (50)
    "james", "john", "robert", "michael", "william", "richard", "joseph",
    "thomas", "charles", "christopher", "matthew", "anthony", "mark", "donald",
    "steven", "paul", "andrew", "joshua", "kenneth", "kevin", "brian", "george",
    "elizabeth", "mary", "jennifer", "linda", "barbara", "susan", "timothy",
    "jessica", "sarah", "karen", "nancy", "lisa", "margaret", "ashley", "emily",
    "dorothy", "michelle", "amanda", "melissa", "deborah", "stephanie",
    "raymond", "gregory", "larry", "jerry", "dennis", "walter", "patrick",
    "peter", "harold", "henry", "carl", "arthur", "albert", "ralph", "roy",
    "catherine", "diane", "ruth", "sharon", "cynthia", "angela", "helen",
    # French (50)
    "jean", "pierre", "marie", "jacques", "michel", "philippe", "alain",
    "nicolas", "françois", "bernard", "patrick", "laurent", "claude",
    "christophe", "étienne", "yves", "thierry", "andré", "marc", "stéphane",
    "catherine", "nathalie", "isabelle", "sophie", "anne", "sylvie", "valérie",
    "christine", "monique", "véronique", "hélène", "florence", "caroline",
    "frédéric", "sébastien", "éric", "olivier", "gérard", "didier", "joël",
    "mathieu", "arnaud", "jérôme", "cédric", "fabrice", "hervé", "gilles",
    "martine", "brigitte", "sandrine", "corinne", "céline", "émilie",
    "charlotte", "camille", "marguerite", "élise", "madeleine", "juliette",
    # German (50)
    "hans", "stefan", "christian", "wolfgang", "martin", "frank",
    "klaus", "jürgen", "werner", "helmut", "uwe", "bernd", "manfred", "dieter",
    "ralf", "matthias", "monika", "ursula", "elisabeth", "helga", "petra",
    "gabriele", "sabine", "susanne", "renate", "birgit", "ingrid", "heike",
    "erika", "julia", "silke", "lena", "nicole", "anja",
    "andreas", "markus", "tobias", "philipp", "florian", "lukas", "maximilian",
    "heinrich", "friedrich", "wilhelm", "karl", "otto", "kurt", "horst",
    "gerhard", "günter", "lothar", "norbert", "volker", "detlef", "axel",
    "gudrun", "hannelore", "elfriede", "lieselotte", "irmgard", "gisela",
    # Italian (50)
    "marco", "giuseppe", "giovanni", "francesco", "luigi", "alessandro",
    "stefano", "mario", "paolo", "carlo", "giorgio", "angelo",
    "franco", "vincenzo", "pietro", "luca", "francesca", "giulia", "paola",
    "valentina", "chiara", "sara", "giovanna", "angela", "lucia", "silvia",
    "daniela", "federica", "monica", "alessandra", "simona", "elisa",
    "matteo", "lorenzo", "andrea", "filippo", "emanuele", "tommaso", "riccardo",
    "davide", "fabio", "massimo", "claudio", "enrico", "maurizio", "nicola",
    "anna", "elena", "barbara", "roberta", "grazia", "ornella", "patrizia",
    "carla", "antonella", "cinzia", "michela", "manuela", "cristina",
    # Portuguese (50)
    "joão", "paulo", "rui", "jorge",
    "tiago", "bruno", "marcos", "fernanda",
    "margarida", "helena", "sofia", "rita", "catarina", "joana",
    "inês", "raquel", "sandra", "cláudia", "filipa", "carolina", "mariana",
    "gonçalo", "diogo", "nuno", "henrique", "gustavo", "rodrigo", "afonso",
    "vasco", "duarte", "tomé", "simão", "bernardo", "lourenço", "vicente",
    "luísa", "alice", "matilde", "leonor", "clara", "francisca", "madalena",
    "vitória", "aurora", "conceição", "fátima", "graça", "celeste",
    "armando", "orlando", "sebastião", "joaquim", "augusto", "baltasar",
    # Dutch (50)
    "jan", "pieter", "dirk", "gerrit", "cornelis", "willem", "hendrik",
    "johannes", "jeroen", "martijn", "bas", "sander", "dennis", "marcel",
    "rob", "wim", "joost", "henk", "kees", "bert", "inge", "miranda",
    "esther", "marion", "yvonne", "wendy", "marleen", "annemarie",
    "michiel", "wouter", "bram", "daan", "thijs", "ruben", "niels", "lars",
    "tim", "arjan", "maarten", "jasper", "joop", "arie", "piet", "geert",
    "els", "tineke", "lotte", "femke", "nienke", "marieke", "maaike",
    "anneke", "rianne", "astrid", "grietje", "truus", "wilma", "corrie",
    # Cross-language common names
    "alexander", "benjamin", "dominique", "emma", "felix",
    "hugo", "ivan", "katarina", "leon", "natalia", "oliver",
    "oscar", "pascal", "samuel", "sebastian", "simon", "victor", "vincent",
    "nikolai", "dimitri", "tatiana", "olga", "sergei", "yuri", "mikhail",
    "eva", "claudia", "peter", "martin", "thomas", "david", "daniel",
}

ALL_SURNAMES = {
    # Spanish (50)
    "garcía", "lópez", "martínez", "gonzález", "rodríguez", "fernández",
    "sánchez", "pérez", "gómez", "martín", "jiménez", "hernández", "díaz",
    "ruiz", "moreno", "álvarez", "muñoz", "romero", "navarro", "torres",
    "domínguez", "vázquez", "ramos", "gil", "ramírez", "serrano", "blanco",
    "molina", "morales", "suárez", "ortega", "delgado", "castro", "ortiz",
    "rubio", "marín", "medina", "iglesias", "santos", "castillo", "garrido",
    "calvo", "peña", "cruz", "cano", "núñez", "cortés", "herrera", "reyes",
    "guerrero", "aguilar", "cabrera", "vargas", "león", "prieto", "fuentes",
    # English (50)
    "smith", "johnson", "williams", "brown", "jones", "davis", "miller",
    "wilson", "moore", "taylor", "anderson", "jackson", "white", "harris",
    "thompson", "martinez", "robinson", "clark", "lewis", "lee", "walker",
    "hall", "allen", "young", "king", "wright", "hill", "scott", "green",
    "adams", "baker", "nelson", "carter", "mitchell", "roberts", "turner",
    "phillips", "campbell", "parker", "evans", "edwards", "collins", "stewart",
    "morris", "murphy", "cook", "rogers", "morgan", "peterson", "cooper",
    "reed", "bailey", "bell", "gomez", "kelly", "howard", "ward", "cox",
    # French (50)
    "bernard", "dubois", "robert", "richard", "petit", "durand", "leroy",
    "moreau", "simon", "lefebvre", "bertrand", "roux", "fournier", "morel",
    "girard", "lefèvre", "mercier", "dupont", "lambert", "bonnet", "muller",
    "faure", "guerin", "robin", "masson", "blanc", "chevalier", "duval",
    "rivière", "gautier", "perrin", "morin", "denis",
    "henry", "rousseau", "legrand", "garnier", "renard", "picard", "brunet",
    "barbier", "arnaud", "lemaire", "caron", "meunier", "collet", "maréchal",
    "gaillard", "aubert", "roy", "clément", "noël", "marchand",
    # German (50)
    "müller", "schmidt", "schneider", "fischer", "weber", "meyer", "wagner",
    "becker", "schulz", "hoffmann", "schäfer", "koch", "bauer", "richter",
    "klein", "wolf", "schröder", "neumann", "schwarz", "zimmermann", "braun",
    "krüger", "hofmann", "hartmann", "lange", "schmitt", "werner", "schmitz",
    "krause", "meier", "lehmann", "schulze", "maier", "köhler", "hermann",
    "könig", "walter", "mayer", "huber", "kaiser", "fuchs", "peters", "lang",
    "frank", "berger", "winkler", "roth", "lorenz", "ludwig", "baumann",
    "schuster", "böhm", "haas", "keller", "vogt", "seidel", "ernst",
    # Italian (50)
    "rossi", "russo", "ferrari", "esposito", "bianchi", "romano", "colombo",
    "ricci", "marino", "greco", "bruno", "gallo", "conti", "costa",
    "giordano", "mancini", "rizzo", "lombardi", "moretti", "barbieri",
    "fontana", "santoro", "mariani", "rinaldi", "caruso", "ferrara", "leone",
    "martinelli", "gentile", "vitale", "conte", "serra", "fabbri", "martini",
    "pellegrini", "grassi", "coppola", "marchetti", "villa", "amato", "bianco",
    "orlando", "ferretti", "pagano", "riva", "sartori", "barone",
    "cattaneo", "valentini", "montanari", "neri", "guerra",
    # Portuguese (50)
    "silva", "oliveira", "souza", "pereira", "rodrigues", "almeida",
    "nascimento", "lima", "araújo", "fernandes", "carvalho", "gomes",
    "martins", "rocha", "ribeiro", "alves", "monteiro", "cardoso", "mendes",
    "barros", "moura", "freitas", "barbosa", "pinto", "moreira", "campos",
    "lopes", "machado", "batista", "teixeira", "nunes", "vieira", "correia",
    "soares", "reis", "cunha", "ferreira", "melo", "azevedo", "marques",
    "duarte", "nogueira", "coelho", "andrade", "braga",
    "tavares", "fonseca", "amorim", "pires", "ramos", "figueiredo", "sampaio",
    "leal", "magalhães", "matos", "brito", "aguiar", "xavier",
    # Dutch (50)
    "jansen", "bakker", "janssen", "visser", "smit", "meijer", "mulder",
    "bos", "vos", "hendriks", "postma", "dijkstra", "smits", "hermans",
    "willems", "dekker", "peeters", "vermeer", "jacobs", "claes", "martens",
    "wouters", "maes", "janssens", "goossens", "pieters", "brouwer",
    "vanderberg", "kuiper", "schouten", "kok", "groen", "gerritsen",
    "timmermans", "huisman", "prins", "dijk", "bosman", "verschoor",
    "wolters", "hoekstra", "boer", "scholten", "dam", "blom", "kramer",
}

SCIENTIFIC_UNIT_NAMES = {
    "newton", "newtons", "kelvin", "kelvins", "watt", "watts",
    "tesla", "teslas", "gauss", "pascal", "pascales", "pascals",
    "ampere", "amperes", "amperio", "amperios", "volt", "volts",
    "voltio", "voltios", "hertz", "joule", "joules", "julio", "julios",
    "coulomb", "coulombs", "farad", "farads", "faradio", "faradios",
    "henry", "henrys", "henrio", "henrios", "ohm", "ohms", "ohmio",
    "ohmios", "siemens", "weber", "webers", "becquerel", "becquerels",
    "gray", "grays", "sievert", "sieverts",
}

TREATMENT_PRECEDING_RE = re.compile(
    r'(?:Dr|Dra|Sr|Sra|Mr|Mrs|Ms|Miss|Prof|Don|Doña|Herr|Frau|Sig|Dott|Dott\.ssa)\.?\s*$',
    re.IGNORECASE
)


EPONYM_TERMS = {
    "síndrome", "enfermedad", "escala", "prueba", "signo", "criterio",
    "criterios", "clasificación", "método", "índice", "técnica", "maniobra",
    "fenómeno", "ley", "modelo", "teorema", "efecto", "reacción", "operación",
    "coeficiente", "distribución", "transformada", "fórmula", "ecuación",
    "principio", "algoritmo", "score", "puntuación",
    "syndrome", "disease", "disorder", "scale", "test", "sign", "criteria",
    "criterion", "classification", "method", "index", "technique", "maneuver",
    "phenomenon", "law", "theorem", "effect", "reaction", "operation",
    "coefficient", "distribution", "transform", "formula", "equation",
    "principle", "algorithm", "score",
    "maladie", "échelle", "signe", "critère", "critères", "méthode",
    "phénomène", "loi", "théorème", "réaction", "coefficient", "formule",
    "équation", "principe", "algorithme",
    "syndrom", "krankheit", "morbus", "skala", "zeichen", "methode",
    "phänomen", "gesetz", "effekt", "reaktion", "koeffizient", "formel",
    "gleichung", "prinzip", "algorithmus",
    "sindrome", "malattia", "scala", "segno", "metodo", "tecnica",
    "fenomeno", "legge", "effetto", "reazione", "operazione", "coefficiente",
    "formula", "equazione", "principio", "algoritmo",
    "síndroma", "doença", "sinal", "fenômeno",
    "efeito", "reação", "operação", "coeficiente", "fórmula", "equação",
    "princípio",
    "syndroom", "ziekte", "schaal", "teken", "techniek",
    "fenomeen", "wet", "reactie", "coëfficiënt", "formule", "vergelijking",
    "principe",
}

EPONYM_CONNECTORS = {"de", "of", "di", "von", "van", "du"}


_IDENTITY_LABEL_TERMS = [
    r"nombre\s+y\s+apellidos", r"nombre\s+completo", r"full\s+name",
    r"nom\s+et\s+prénom", r"nome\s+e\s+cognome",
    r"apellidos?", r"nombre", r"titular", r"paciente", r"representante",
    r"firmado\s+por", r"firma", r"autor(?:a)?", r"atendido\s+por",
    r"responsable", r"contacto",
    r"(?:patient\s+)?name", r"surname", r"patient", r"signed?\s+by",
    r"signature", r"author", r"attended\s+by", r"investigator",
    r"contact(?:\s+person)?",
    r"nom", r"prénom", r"signé\s+par", r"auteur",
    r"vorname", r"nachname", r"unterschrift", r"verantwortlich",
    r"cognome", r"paziente", r"firmato\s+da", r"autore",
    r"apelido", r"assinado\s+por", r"assinatura",
    r"voornaam", r"achternaam", r"patiënt", r"ondertekend\s+door",
    r"handtekening",
]

_STRONG_CONTEXT_TERMS = [
    r"firmado\s+por", r"firma", r"autor(?:a)?", r"responsable",
    r"atendido\s+por", r"investigador(?:a)?",
    r"signed?\s+by", r"signature", r"author", r"attended\s+by",
    r"investigator", r"principal\s+investigator",
    r"signé\s+par", r"auteur", r"unterschrift",
    r"firmato\s+da", r"autore", r"assinado\s+por", r"assinatura",
    r"ondertekend\s+door", r"handtekening",
]

NAME_PARTICLES = {
    "de", "del", "de la", "de los", "de las", "da", "do", "dos", "das",
    "di", "della", "dello", "dei", "von", "zu", "van", "van de", "van der",
    "van den", "du", "des", "y", "i", "e",
}
_PARTICLES_SORTED = sorted(NAME_PARTICLES, key=len, reverse=True)
_PARTICLES_RE_STR = '|'.join(
    p.replace(' ', r'\s+') for p in _PARTICLES_SORTED
)
_CAP = r'[A-ZÀ-ÿ][a-zà-ÿ]+'
_NAME_SEGMENT = rf'(?:\s+(?:{_PARTICLES_RE_STR})\s+{_CAP}|\s+{_CAP})'


_LABEL_TERMS_RE = '|'.join(_IDENTITY_LABEL_TERMS)
PERSON_LABEL_RE = re.compile(
    rf'(?i:{_LABEL_TERMS_RE})\s*[:=]\s*({_CAP}(?:{_NAME_SEGMENT}{{0,3}}))',
    re.UNICODE
)

_UPPER_CAP = r'[A-ZÀ-ÿ]{2,}'
_UPPER_NAME_SEGMENT = rf'(?:\s+(?:{_PARTICLES_RE_STR})\s+{_UPPER_CAP}|\s+{_UPPER_CAP})'
PERSON_LABEL_UPPER_RE = re.compile(
    rf'(?i:{_LABEL_TERMS_RE})\s*[:=]\s*({_UPPER_CAP}(?:{_UPPER_NAME_SEGMENT}{{0,3}}))',
    re.UNICODE
)

_STRONG_RE_STR = '|'.join(_STRONG_CONTEXT_TERMS)
PERSON_INITIAL_RE = re.compile(
    rf'(?i:{_STRONG_RE_STR})\s*[:=]\s*'
    rf'([A-ZÀ-ÿ]\.\s*(?:(?:{_PARTICLES_RE_STR})\s+)?{_CAP}(?:\s+{_CAP})?)',
    re.UNICODE
)


_EPONYM_TERMS_SORTED = '|'.join(
    re.escape(t) for t in sorted(EPONYM_TERMS, key=len, reverse=True)
)
_EPONYM_CONNS_SORTED = '|'.join(
    re.escape(c) for c in sorted(EPONYM_CONNECTORS, key=len, reverse=True)
)
EPONYM_BEFORE_RE = re.compile(
    rf'\b(?:{_EPONYM_TERMS_SORTED})\s+(?:{_EPONYM_CONNS_SORTED})\s*$',
    re.IGNORECASE
)
EPONYM_DIRECT_RE = re.compile(
    rf'\b(?:{_EPONYM_TERMS_SORTED})\s*$',
    re.IGNORECASE
)
EPONYM_AFTER_RE = re.compile(
    rf"^(?:'s\s+)?(?:{_EPONYM_TERMS_SORTED})",
    re.IGNORECASE
)

# ============================================================================
# PRECOMPILED REGEX PATTERNS (for performance)
# ============================================================================

def _compile_pattern_list(patterns, flags=re.IGNORECASE):
    """Compile a list of pattern strings into regex objects."""
    return [re.compile(p, flags) for p in patterns]

def _compile_pattern_dict(patterns, flags=re.IGNORECASE):
    """Compile a dict of pattern strings into regex objects."""
    return {name: re.compile(p, flags) for name, p in patterns.items()}

# Compile all pattern lists
CLINICAL_TRIAL_PATTERNS_RE = _compile_pattern_dict(CLINICAL_TRIAL_PATTERNS)
CASE_SENSITIVE_PATTERNS_RE = _compile_pattern_dict(CASE_SENSITIVE_PATTERNS, flags=0)  # No IGNORECASE - uppercase only
CLINICAL_ABBREVIATIONS_RE = _compile_pattern_list(CLINICAL_ABBREVIATIONS_WITH_VALUE)
HOSPITAL_RE = _compile_pattern_list(HOSPITAL_PATTERNS, flags=0)
PHARMA_COMPANY_RE = _compile_pattern_list(PHARMA_COMPANY_PATTERNS)
CRO_RE = _compile_pattern_list(CRO_PATTERNS)
BLOCKBUSTER_DRUGS_RE = _compile_pattern_list(BLOCKBUSTER_DRUGS)
CLINICAL_TECH_RE = _compile_pattern_list(CLINICAL_TECH_PLATFORMS)
CENTRAL_LABS_RE = _compile_pattern_list(CENTRAL_LABS)
LAB_PRODUCT_RE = _compile_pattern_list(LAB_PRODUCT_PATTERNS)
ACRONYM_RE = _compile_pattern_list(ACRONYM_PATTERNS, flags=0)  # No IGNORECASE - pattern requires uppercase
SOFTWARE_PRODUCT_RE = _compile_pattern_list(SOFTWARE_PRODUCT_PATTERNS, flags=0)
URL_RE = _compile_pattern_list(URL_PATTERNS)
CLINICAL_URL_RE = _compile_pattern_list(CLINICAL_URL_PATTERNS)
ADDRESS_RE = _compile_pattern_list(ADDRESS_PATTERNS)
INVESTIGATOR_RE = _compile_pattern_list(INVESTIGATOR_PATTERNS, flags=0)  # No IGNORECASE - pattern defines case explicitly
CLINICAL_DATE_RE = _compile_pattern_list(CLINICAL_DATE_PATTERNS)
LOT_BATCH_RE = _compile_pattern_list(LOT_BATCH_PATTERNS)
SITE_CODE_RE = _compile_pattern_list(SITE_CODE_PATTERNS)
IRB_ETHICS_RE = _compile_pattern_list(IRB_ETHICS_PATTERNS, flags=0)
AGE_RANGE_RE = _compile_pattern_list(AGE_RANGE_PATTERNS)
COUNTRY_NATIONALITY_RE = _compile_pattern_list(COUNTRY_NATIONALITY_PATTERNS)
STUDY_NAME_RE = _compile_pattern_list(STUDY_NAME_PATTERNS)
RANDOMIZATION_RE = _compile_pattern_list(RANDOMIZATION_PATTERNS)
MEDICAL_DEVICE_RE = _compile_pattern_list(MEDICAL_DEVICE_PATTERNS, flags=0)
INTERNATIONAL_PHONE_RE = _compile_pattern_list(INTERNATIONAL_PHONE_PATTERNS)
CORPORATE_EMAIL_RE = _compile_pattern_list(CORPORATE_EMAIL_PATTERNS)
POSTAL_CODE_RE = _compile_pattern_list(POSTAL_CODE_PATTERNS)
DOB_RE = _compile_pattern_list(DOB_PATTERNS)
CRITICAL_PII_RE = _compile_pattern_list(CRITICAL_PII_PATTERNS)
SAFE_REGEX_PATTERNS_RE = _compile_pattern_dict(SAFE_REGEX_PATTERNS)
SAFE_REGEX_PHONE_RE = _compile_pattern_list(SAFE_REGEX_PHONE_PATTERNS)
SAFE_REGEX_ADDRESS_RE = _compile_pattern_list(SAFE_REGEX_ADDRESS_PATTERNS, flags=0)
SAFE_REGEX_POSTAL_RE = _compile_pattern_list(SAFE_REGEX_POSTAL_PATTERNS)
SAFE_REGEX_TITLED_NAME_RE = _compile_pattern_list(SAFE_REGEX_TITLED_NAME_PATTERNS, flags=0)
SAFE_REGEX_DOB_RE = _compile_pattern_list(SAFE_REGEX_DOB_PATTERNS)
SAFE_REGEX_CJK_TITLED_NAME_RE = _compile_pattern_list(SAFE_REGEX_CJK_TITLED_NAME_PATTERNS, flags=0)
SAFE_REGEX_CJK_ADDRESS_RE = _compile_pattern_list(SAFE_REGEX_CJK_ADDRESS_PATTERNS, flags=0)
SAFE_REGEX_CJK_PHONE_RE = _compile_pattern_list(SAFE_REGEX_CJK_PHONE_PATTERNS, flags=0)

# Emails and URLs must be redacted as atomic units *before* any token-level
# layer (custom dictionary, biomedical org names) runs. Otherwise a term
# embedded inside an address (a blacklisted word appearing in an email
# local-part or domain) gets replaced on its own, which breaks the surrounding
# email/URL pattern and leaks the rest of the address. The corporate-email
# patterns are a subset of the generic EMAIL pattern, so EMAIL + the two URL
# patterns are sufficient.
EMAIL_URL_GUARD_RE = [
    SAFE_REGEX_PATTERNS_RE[k]
    for k in ("EMAIL", "URL_HTTPS", "URL_DOMAIN")
    if k in SAFE_REGEX_PATTERNS_RE
]

# Helper functions for working with compiled patterns
def _findall_compiled_list(compiled_list, text):
    """Find all matches from a list of compiled patterns."""
    results = []
    for compiled in compiled_list:
        results.extend(compiled.findall(text))
    return results

def _sub_compiled_list(compiled_list, replacement, text):
    """Apply substitutions from a list of compiled patterns, returns (text, count)."""
    count = 0
    for compiled in compiled_list:
        matches = compiled.findall(text)
        if matches:
            count += len(matches)
            text = compiled.sub(lambda m: replacement, text)
    return text, count

def _sub_compiled_dict(compiled_dict, replacement, text):
    """Apply substitutions from a dict of compiled patterns, returns (text, count)."""
    count = 0
    for name, compiled in compiled_dict.items():
        matches = compiled.findall(text)
        if matches:
            count += len(matches)
            text = compiled.sub(lambda m: replacement, text)
    return text, count



@within_run
def _dictionary_patterns(terms):
    return tuple(re.compile(r'(?<!\w)' + re.escape(t) + r'(?!\w)', re.IGNORECASE)
                 for t in sorted(terms, key=lambda x: (-len(x), x)))

def document_scope(fn):
    @wraps(fn)
    @analysis_scope
    def wrapped(self,*args,**kwargs):
        self._document_active=True
        try:return fn(self,*args,**kwargs)
        finally:
            self.terms_cache.clear();self.lowercase_words.clear()
            self._cache_regex=None;self._cache_dirty=True;self._document_active=False
    return wrapped

class MQXLIFFAnonymizer:
    def __init__(self, replacement_token: str = "███", propagate_terms: bool = True):
        self.propagate_terms=propagate_terms
        self._document_active=False
        if not replacement_token or not replacement_token.strip() or re.search(r'[\x00-\x1f\uE000-\uF8FF]', replacement_token):
            raise ValueError("Replacement token must be non-empty and contain no control/private-use characters.")
        self.replacement_token = replacement_token
        self.stats = {
            "safe_regex": 0,
            "regex_ct": 0,
            "proper_names": 0,
            "dictionary": 0,
            "critical_pii_remaining": {},
            "timings": {
                "total_ms": 0.0,
                "segments": 0,
                "last_segment_ms": 0.0
            }
        }
        self.terms_cache = set()
        self.lowercase_words = set()
        self._cache_regex = None
        self._cache_dirty = True
        self.strict_validation = False
        self.enable_benchmark = False
    
    def reset_stats(self):
        self.stats = {
            "safe_regex": 0,
            "regex_ct": 0,
            "proper_names": 0,
            "dictionary": 0,
            "critical_pii_remaining": {},
            "timings": {
                "total_ms": 0.0,
                "segments": 0,
                "last_segment_ms": 0.0
            }
        }
        self.terms_cache = set()
        self.lowercase_words = set()
        self._cache_regex = None
        self._cache_dirty = True
    
    def _scan_document_for_lowercase(self, tree):
        """Scan document to find all words that appear in lowercase.
        Used to validate cache - if a term appears lowercase anywhere, it's not a proper noun.
        Excludes content from emails and URLs to avoid false lowercase detection."""
        trans_units = tree.xpath("//xliff:trans-unit", namespaces=XLIFF_NS)
        
        email_url_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|'
            r'https?://[^\s]+|'
            r'www\.[^\s]+|'
            r'[a-zA-Z0-9.-]+\.(com|org|net|edu|gov|io|co|es|de|fr|uk|eu)[^\s]*',
            re.IGNORECASE
        )
        
        for tu in trans_units:
            for elem in tu.xpath(".//xliff:source | .//xliff:target", namespaces=XLIFF_NS):
                text = "".join(elem.itertext())
                if text:
                    clean_text = email_url_pattern.sub(' ', text)
                    words = re.findall(r'\b[a-záéíóúñüàèìòùäëïöü]+\b', clean_text, re.IGNORECASE)
                    for word in words:
                        if word.islower() and len(word) > 2:
                            self.lowercase_words.add(word.lower())
    
    def _should_block_cache_candidate(self, span_text: str, doc_span, lang: str) -> bool:
        """
        Devuelve True si NO deberíamos cachear un candidato (para evitar falsos positivos).
        Heuristics only (spaCy/NER layers were removed from the product).
        """
        if not span_text:
            return True

        tokens = span_text.strip().split()
        if not tokens:
            return True

        stopwords = STOPWORDS_FUNCTIONAL_EN if lang == "en" else STOPWORDS_FUNCTIONAL_ES
        common_block = COMMON_SINGLETON_BLOCK_EN if lang == "en" else COMMON_SINGLETON_BLOCK_ES

        lower_tokens = [str(x).lower() for x in tokens]

        # Regla 1: 1 token que es stopword funcional → bloquear
        if len(lower_tokens) == 1 and lower_tokens[0] in stopwords:
            return True

        # Regla 2: 1 token que es sustantivo común bloqueado → bloquear SIEMPRE
        if len(lower_tokens) == 1 and lower_tokens[0] in common_block:
            return True

        # Regla 3: 2 tokens con stopword + common_block → bloquear (ej: "The System", "El Sistema")
        if len(lower_tokens) == 2:
            has_stopword = any(t in stopwords for t in lower_tokens)
            has_common_block = any(t in common_block for t in lower_tokens)
            all_common_block = all(t in common_block for t in lower_tokens)
            if has_stopword and has_common_block:
                return True
            if all_common_block:
                return True
            if has_stopword:
                return True

        return False
    
    def _add_to_cache(self, term: str, lang: str = "en", doc_span=None):
        """Add a detected term to the cache for consistent anonymization.
        
        v10.0: Integra _should_block_cache_candidate() para mejor filtrado.
        Heuristics only (spaCy/NER validation removed with the NLP layers).
        """
        if not self._document_active or not self.propagate_terms:return
        term_strip = term.strip()
        if len(term_strip) < 4 or self.replacement_token in term_strip:
            return

        words = term_strip.split()
        num_words = len(words)
        key = term_strip.lower()

        # v10.0: Usar el nuevo sistema de bloqueo
        if self._should_block_cache_candidate(term_strip, doc_span, lang):
            return

        def is_titlecase_word(w: str) -> bool:
            return len(w) >= 2 and w[0].isupper() and w[1:].islower()

        title_case_count = sum(1 for w in words if is_titlecase_word(w))
        has_digits_hyphens = bool(re.search(r"[\d_-]", term_strip))
        is_acronym = term_strip.isupper() and len(term_strip) >= 3

        only_first_capitalized = (
            num_words > 1
            and words[0][:1].isupper()
            and all(w[:1].islower() for w in words[1:] if w)
        )

        if num_words >= 2:
            if title_case_count >= 2:
                if key not in self.terms_cache:
                    self.terms_cache.add(key)
                    self._cache_dirty = True
                return

            has_strong_evidence = has_digits_hyphens or is_acronym

            # Inicio de oración (solo primera palabra capitalizada): más estricto
            if only_first_capitalized and not (has_digits_hyphens or is_acronym):
                return

            if not has_strong_evidence:
                return

        else:
            # single-word: muy estricto
            if len(term_strip) < 3:
                return
            if not (is_acronym or has_digits_hyphens):
                return

        # Añadir al cache
        if key not in self.terms_cache:
            self.terms_cache.add(key)
            self._cache_dirty = True
    
    def _build_cache_regex(self):
        """Build a single compiled regex from all cached terms."""
        if not self.terms_cache or len(self.terms_cache) > 10000:
            self._cache_regex = None
            return
        
        sorted_terms = sorted(self.terms_cache, key=len, reverse=True)
        escaped_terms = [r'(?<![A-Za-z0-9À-ÿ])' + re.escape(t) + r'(?![A-Za-z0-9À-ÿ])' for t in sorted_terms]
        pattern = '|'.join(escaped_terms)
        self._cache_regex = re.compile(pattern, re.IGNORECASE)
        self._cache_dirty = False

    def _apply_cache(self, text: str) -> str:
        """Apply cached terms using optimized single-pass regex."""
        if not self.terms_cache:
            return text
        
        if self._cache_dirty or self._cache_regex is None:
            self._build_cache_regex()
        
        if self._cache_regex is None:
            # Fallback for very large caches (>10k terms)
            result = text
            for term in sorted(self.terms_cache, key=len, reverse=True):
                pattern = r'(?<![A-Za-z0-9À-ÿ])' + re.escape(term) + r'(?![A-Za-z0-9À-ÿ])'
                def _fallback_replace(m):
                    matched = m.group(0)
                    if matched.islower():
                        return matched
                    fb_words = [w for w in re.findall(r'[a-záéíóúñüàèìòùäëïöü]+', matched.lower(), re.IGNORECASE) if len(w) > 2]
                    if fb_words and self.lowercase_words and all(w in self.lowercase_words for w in fb_words):
                        return matched
                    self.stats["regex_ct"] += 1
                    return self.replacement_token
                result = re.sub(pattern, _fallback_replace, result, flags=re.IGNORECASE)
            return result
        
        def replace_match(m):
            matched = m.group(0)
            if matched.islower():
                return matched
            match_words = [w for w in re.findall(r'[a-záéíóúñüàèìòùäëïöü]+', matched.lower(), re.IGNORECASE) if len(w) > 2]
            if match_words and self.lowercase_words and all(w in self.lowercase_words for w in match_words):
                return matched
            self.stats["regex_ct"] += 1
            return self.replacement_token
        
        return self._cache_regex.sub(replace_match, text)

    def _apply_cache_to_element(self, element):
        whitelist = getattr(self, '_active_whitelist', set())
        def transform(text):
            protected, replacements = self._protect_whitelist_terms(text, whitelist)
            return self._restore_whitelist_placeholders(self._apply_cache(protected), replacements)
        rewrite_element(element, transform)

    def _mask_pii_example(self, text: str, pii_type: str) -> str:
        """Mask PII for safe logging (e.g., j***@d***.com, ***1234 for IDs)."""
        if pii_type == "email" and "@" in text:
            parts = text.split("@")
            user = parts[0][0] + "***" if parts[0] else "***"
            domain_parts = parts[1].split(".") if len(parts) > 1 else ["***", "com"]
            domain = domain_parts[0][0] + "***" if domain_parts[0] else "***"
            tld = domain_parts[-1] if len(domain_parts) > 1 else "com"
            return f"{user}@{domain}.{tld}"
        elif pii_type == "phone":
            digits = re.sub(r'\D', '', text)
            return "***" + digits[-3:] if len(digits) >= 3 else "***"
        elif pii_type == "url":
            match = re.match(r'(https?://)?([^/]+)', text)
            if match:
                return (match.group(1) or "") + match.group(2)[:10] + "***"
            return text[:10] + "***"
        elif pii_type in ["clinical_id", "eudract_id"]:
            # Show only last 4 characters for clinical IDs (e.g., ***1234)
            return "***" + text[-4:] if len(text) >= 4 else "***"
        else:
            return text[:3] + "***" + text[-2:] if len(text) > 5 else "***"

    def _validate_no_critical_pii(self, text: str) -> dict:
        """Post-scan to detect any PII that escaped the pipeline."""
        categories = {
            "email": CRITICAL_PII_RE[0],
            "phone": CRITICAL_PII_RE[1],
            "url": CRITICAL_PII_RE[2],
            "clinical_id": CRITICAL_PII_RE[3],
            "eudract_id": CRITICAL_PII_RE[4],
        }
        
        counts = {}
        examples = {}
        
        for cat_name, pattern in categories.items():
            matches = pattern.findall(text)
            # Filter out matches that are just the replacement token
            real_matches = [m for m in matches if self.replacement_token not in m]
            counts[cat_name] = len(real_matches)
            if real_matches:
                examples[cat_name] = [self._mask_pii_example(m, cat_name) for m in real_matches[:3]]
        
        return {"counts": counts, "examples": examples}
    
    def anonymize_with_safe_regex(self, text: str, lang: str = "en") -> str:
        result = text

        result, sr_count = _sub_compiled_dict(SAFE_REGEX_PATTERNS_RE, self.replacement_token, result)
        self.stats["safe_regex"] += sr_count

        result, ph_count = _sub_compiled_list(SAFE_REGEX_PHONE_RE, self.replacement_token, result)
        self.stats["safe_regex"] += ph_count

        result, addr_count = _sub_compiled_list(SAFE_REGEX_ADDRESS_RE, self.replacement_token, result)
        self.stats["safe_regex"] += addr_count

        result, postal_count = _sub_compiled_list(SAFE_REGEX_POSTAL_RE, self.replacement_token, result)
        self.stats["safe_regex"] += postal_count

        result, name_count = _sub_compiled_list(SAFE_REGEX_TITLED_NAME_RE, self.replacement_token, result)
        self.stats["safe_regex"] += name_count

        result, dob_count = _sub_compiled_list(SAFE_REGEX_DOB_RE, self.replacement_token, result)
        self.stats["safe_regex"] += dob_count

        result, cjk_name_count = _sub_compiled_list(SAFE_REGEX_CJK_TITLED_NAME_RE, self.replacement_token, result)
        self.stats["safe_regex"] += cjk_name_count

        result, cjk_addr_count = _sub_compiled_list(SAFE_REGEX_CJK_ADDRESS_RE, self.replacement_token, result)
        self.stats["safe_regex"] += cjk_addr_count

        result, cjk_ph_count = _sub_compiled_list(SAFE_REGEX_CJK_PHONE_RE, self.replacement_token, result)
        self.stats["safe_regex"] += cjk_ph_count

        return result

    def anonymize_with_proper_names(self, text: str, lang: str = "en") -> str:
        result = text

        result, person_count = self._detect_person_names_safe(result, lang)
        self.stats["proper_names"] += person_count

        result, hosp_count = _sub_compiled_list(HOSPITAL_RE, self.replacement_token, result)
        self.stats["proper_names"] += hosp_count

        return result


    def _detect_person_names_safe(self, text: str, lang: str = "en") -> Tuple[str, int]:
        if not text or len(text) < 5:
            return text, 0

        count = 0
        replacements = []

        for label_re in (PERSON_LABEL_RE, PERSON_LABEL_UPPER_RE):
            for m in label_re.finditer(text):
                name_text = m.group(1).strip()
                tokens = name_text.split()
                name_tokens = [t for t in tokens if t.lower() not in NAME_PARTICLES]
                if not name_tokens:
                    continue
                has_list_evidence = any(
                    t.lower() in ALL_FIRST_NAMES or t.lower() in ALL_SURNAMES
                    for t in name_tokens
                )
                if not has_list_evidence:
                    continue
                start, end = m.start(1), m.end(1)
                if not self._name_overlaps(replacements, start, end):
                    replacements.append((start, end, name_text))

        for m in PERSON_INITIAL_RE.finditer(text):
            name_text = m.group(1).strip()
            start, end = m.start(1), m.end(1)
            if not self._name_overlaps(replacements, start, end):
                replacements.append((start, end, name_text))

        cap_re = re.compile(r'[A-ZÀ-ÿ][a-zà-ÿ]+')
        cap_matches = [(m.start(), m.end(), m.group()) for m in cap_re.finditer(text)]
        scored_candidates = []

        for i in range(len(cap_matches)):
            for group_size in range(2, 5):
                group = [cap_matches[i]]
                valid = True
                for k in range(1, group_size):
                    idx = i + k
                    if idx >= len(cap_matches):
                        valid = False
                        break
                    prev_end = group[-1][1]
                    curr_start = cap_matches[idx][0]
                    between = text[prev_end:curr_start]
                    gap = between.strip()
                    if len(between) > 15 or (gap and gap.lower() not in NAME_PARTICLES):
                        valid = False
                        break
                    group.append(cap_matches[idx])

                if not valid or len(group) < 2:
                    continue

                cand_start = group[0][0]
                cand_end = group[-1][1]
                candidate = text[cand_start:cand_end]

                if self._name_overlaps(replacements, cand_start, cand_end):
                    continue

                if self._is_eponym_context(text, cand_start, cand_end):
                    continue

                if self._is_scientific_unit_context(text, cand_start, cand_end, candidate):
                    continue

                tokens = candidate.split()
                name_tokens = [t for t in tokens if t.lower() not in NAME_PARTICLES]

                if len(name_tokens) < 2:
                    continue

                score = self._score_person_candidate(
                    name_tokens, tokens, text, cand_start, cand_end
                )

                if score >= 6:
                    scored_candidates.append(
                        (score, cand_end - cand_start, cand_start, cand_end, candidate)
                    )

        scored_candidates.sort(key=lambda x: (-x[0], -x[1]))
        for score_val, length, cand_start, cand_end, candidate in scored_candidates:
            if not self._name_overlaps(replacements, cand_start, cand_end):
                replacements.append((cand_start, cand_end, candidate))

        for start, end, matched in sorted(
            replacements, key=lambda x: x[0], reverse=True
        ):
            text = text[:start] + self.replacement_token + text[end:]
            count += 1
            self._add_to_cache(matched, lang=lang)
            for token in matched.split():
                tc = token.strip()
                if (len(tc) >= 3 and tc[0].isupper()
                        and tc.lower() not in NAME_PARTICLES):
                    self._add_to_cache(tc, lang=lang)

        return text, count

    def _score_person_candidate(
        self, name_tokens: list, all_tokens: list,
        text: str, start: int, end: int
    ) -> int:
        score = 0

        if len(name_tokens) >= 3:
            score += 4
        else:
            score += 3

        first_lower = name_tokens[0].lower()
        last_lower = name_tokens[-1].lower()

        if first_lower in ALL_FIRST_NAMES:
            score += 2
        if last_lower in ALL_SURNAMES:
            score += 2

        has_particle = any(t.lower() in NAME_PARTICLES for t in all_tokens)
        if has_particle:
            score += 1

        preceding_30 = text[max(0, start - 30):start]
        has_treatment = bool(TREATMENT_PRECEDING_RE.search(preceding_30))

        if first_lower not in ALL_FIRST_NAMES and not has_treatment:
            score -= 3

        if self._name_at_sentence_start(text, start):
            if first_lower not in ALL_FIRST_NAMES:
                score -= 2

        return score

    @staticmethod
    def _name_overlaps(replacements: list, start: int, end: int) -> bool:
        for s, e, _ in replacements:
            if start < e and end > s:
                return True
        return False

    @staticmethod
    def _name_at_sentence_start(text: str, start: int) -> bool:
        if start == 0:
            return True
        preceding = text[:start].rstrip()
        if not preceding:
            return True
        return preceding[-1] in '.!?'

    def _is_eponym_context(self, text: str, start: int, end: int) -> bool:
        preceding = text[max(0, start - 60):start]
        if EPONYM_BEFORE_RE.search(preceding):
            return True
        if EPONYM_DIRECT_RE.search(preceding):
            return True

        following = text[end:end + 40].lstrip()
        if EPONYM_AFTER_RE.match(following):
            return True

        return False

    @staticmethod
    def _is_scientific_unit_context(text: str, start: int, end: int,
                                     candidate: str) -> bool:
        tokens = candidate.lower().split()
        has_unit = any(t in SCIENTIFIC_UNIT_NAMES for t in tokens)
        if not has_unit:
            return False
        preceding = text[max(0, start - 20):start]
        following = text[end:end + 20]
        if re.search(r'\d[\d.,]*\s*$', preceding):
            return True
        if re.search(r'^\s*\d', following):
            return True
        if re.search(r'[=<>≤≥±~∼×÷/%°]\s*$', preceding):
            return True
        if re.search(r'^\s*[=<>≤≥±~∼×÷/%°]', following):
            return True
        all_lower = all(not c.isupper() for c in candidate if c.isalpha())
        if all_lower:
            return True
        return False


    def anonymize_with_regex_ct(self, text: str, lang: str = "en") -> str:
        """Anonymize clinical trial IDs using precompiled patterns."""
        result = text
        
        # Use compiled clinical trial patterns
        result, ct_count = _sub_compiled_dict(CLINICAL_TRIAL_PATTERNS_RE, self.replacement_token, result)
        self.stats["regex_ct"] += ct_count
        
        # Use case-sensitive patterns (alphanumeric codes) - must be uppercase only
        result, cs_count = _sub_compiled_dict(CASE_SENSITIVE_PATTERNS_RE, self.replacement_token, result)
        self.stats["regex_ct"] += cs_count
        
        acronym_re = ACRONYM_ALLCAPS_RE
        for m in reversed(list(acronym_re.finditer(result))):
            matched = m.group(0)
            if matched in SAFE_ACRONYMS or matched == self.replacement_token.upper():
                continue
            result = result[:m.start()] + self.replacement_token + result[m.end():]
            self.stats["regex_ct"] += 1
        
        # Use compiled clinical abbreviations
        result, abbrev_count = _sub_compiled_list(CLINICAL_ABBREVIATIONS_RE, self.replacement_token, result)
        self.stats["regex_ct"] += abbrev_count
        
        # Software products - collect matches using compiled patterns
        all_matches = []
        for compiled in SOFTWARE_PRODUCT_RE:
            matches = compiled.findall(result)
            for match in matches:
                if match not in all_matches:
                    all_matches.append(match)
        
        all_matches.sort(key=len, reverse=True)
        
        for match in all_matches:
            if match not in result:
                continue
            words = match.split()
            if words and words[0].lower() in INSTRUCTION_VERBS:
                clean_match = ' '.join(words[1:])
                if clean_match:
                    self._add_to_cache(clean_match, lang=lang)
                    esc_re = re.compile(re.escape(match), re.IGNORECASE)
                    result = esc_re.sub(lambda m: words[0] + ' ' + self.replacement_token, result)
                    self.stats["regex_ct"] += 1
            else:
                self._add_to_cache(match, lang=lang)
                self.stats["regex_ct"] += 1
                esc_re = re.compile(re.escape(match), re.IGNORECASE)
                result = esc_re.sub(lambda m: self.replacement_token, result)
        
        return result
    
    def anonymize_with_dictionary(self, text: str, terms: Set[str]) -> str:
        if not terms:
            return text
        key = tuple(sorted(t.strip() for t in terms if t.strip()))
        for pattern in _dictionary_patterns(key):
            text, count = pattern.subn(lambda m: self.replacement_token, text)
            self.stats['dictionary'] += count
        return text
    
    def _guard_emails_with_terms(self, text: str, terms: Set[str]) -> Tuple[str, int]:
        """Redact whole emails/URLs that contain a blacklisted term.

        Used as a prepass when the Safe Regex layer is off: the dictionary
        layer matches terms on word boundaries, so a blacklisted word inside an
        address (e.g. a company name in the domain) would be replaced on its own
        and leave a leaking fragment like ``user@[X].com``. Here we detect any
        address whose text contains a term (using the same word-boundary rule as
        the dictionary) and redact the whole address atomically. Addresses with
        no blacklisted term are left untouched, respecting the off toggle.
        """
        cleaned = [t.strip() for t in terms if t and t.strip()]
        if not cleaned:
            return text, 0
        term_res = _dictionary_patterns(tuple(sorted(cleaned)))
        count = 0

        def _repl(m):
            nonlocal count
            matched = m.group(0)
            if any(tr.search(matched) for tr in term_res):
                count += 1
                return self.replacement_token
            return matched

        for compiled in EMAIL_URL_GUARD_RE:
            text = compiled.sub(_repl, text)
        return text, count
    
    def _make_wl_placeholder(self, counter: int) -> str:
        digits = f"{counter:06d}"
        encoded = ''.join(chr(0xE010 + int(d)) for d in digits)
        return f"\uE000{encoded}\uE001"

    def _protect_whitelist_terms(self, text: str, whitelist_terms: Set[str]) -> Tuple[str, List[Tuple[str, str]]]:
        if not whitelist_terms:
            return text, []
        
        replacements = []
        sorted_terms = sorted(whitelist_terms, key=len, reverse=True)
        counter = getattr(self, '_whitelist_counter', 0)
        self._whitelist_counter = counter + len(text) + len(sorted_terms) + 1
        for term in sorted_terms:
            pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
            matches = list(pattern.finditer(text))
            if matches:
                for match in reversed(matches):
                    placeholder = self._make_wl_placeholder(counter)
                    counter += 1
                    original_match = match.group(0)
                    replacements.append((placeholder, original_match))
                    text = text[:match.start()] + placeholder + text[match.end():]
        
        return text, replacements
    
    def _restore_whitelist_placeholders(self, text: str, replacements: List[Tuple[str, str]]) -> str:
        for placeholder, original in replacements:
            text = text.replace(placeholder, original)
        return text
    
    def _consolidate_tokens(self, text: str) -> str:
        token = re.escape(self.replacement_token)
        pattern = rf'{token}(?:\s*[,;.\-–—/|]\s*{token}|\s+{token}|\s*\(\s*{token}\s*\))+'
        text = re.sub(pattern, lambda m: self.replacement_token, text)
        return text


    def process_text_node(self, text: str, 
                          lang: str = "en",
                          use_safe_regex: bool = True,
                          use_regex: bool = True,
                          use_proper_names: bool = False,
                          use_dictionary: bool = True,
                          dictionary_terms: Set[str] = None,
                          whitelist_terms: Set[str] = None) -> str:
        start_time = time.perf_counter()
        
        if not text or not text.strip():
            return text
        
        self._active_whitelist = whitelist_terms or set()
        # Whole addresses may be explicitly protected; fragments may not break an address detector.
        atomic_terms = {t for t in (whitelist_terms or set())
                        if any(p.fullmatch(t) for p in EMAIL_URL_GUARD_RE)}
        text, wl_placeholders = self._protect_whitelist_terms(text, atomic_terms)
        result = text
        
        # Guard emails/URLs as atomic units before the dictionary (and any other
        # token-level layer) can redact a company name embedded inside them and
        # break the surrounding match.
        if use_safe_regex:
            # Safe Regex on: redact ALL emails/URLs atomically.
            result, guard_cnt = _sub_compiled_list(EMAIL_URL_GUARD_RE, self.replacement_token, result)
            self.stats["safe_regex"] += guard_cnt
        elif use_dictionary and dictionary_terms:
            # Safe Regex off: the dictionary would otherwise redact a blacklisted
            # term embedded in an address on its own, shredding the email/URL
            # and leaking the rest. Atomically redact only the
            # addresses that actually contain a blacklisted term.
            result, guard_cnt = self._guard_emails_with_terms(result, dictionary_terms)
            self.stats["dictionary"] += guard_cnt
        
        if whitelist_terms:
            result, other_placeholders = self._protect_whitelist_terms(result, whitelist_terms - atomic_terms)
            wl_placeholders.extend(other_placeholders)
        if use_dictionary and dictionary_terms:
            result = self.anonymize_with_dictionary(result, dictionary_terms)
        
        if use_safe_regex:
            result = self.anonymize_with_safe_regex(result, lang=lang)
        
        if use_regex:
            result = self.anonymize_with_regex_ct(result, lang=lang)
        
        if use_proper_names:
            result = self.anonymize_with_proper_names(result, lang=lang)
        
        if use_regex:
            result = self._apply_cache(result)
        
        if wl_placeholders:
            result = self._restore_whitelist_placeholders(result, wl_placeholders)
        
        if use_safe_regex:
            result = self._consolidate_tokens(result)
        
        # Validate no critical PII remaining
        pii_check = self._validate_no_critical_pii(result)
        if any(pii_check["counts"].values()):
            existing = self.stats.setdefault('critical_pii_remaining', {})
            counts = existing.setdefault('counts', {})
            examples = existing.setdefault('examples', {})
            for cat, count in pii_check['counts'].items():
                counts[cat] = counts.get(cat, 0) + count
            for cat, vals in pii_check['examples'].items():
                examples[cat] = list(dict.fromkeys(examples.get(cat, []) + vals))[:3]
            # Strict mode: raise error if critical PII remains
            if self.strict_validation:
                raise ValueError(f"Critical PII remained after anonymization: {pii_check['counts']}")

        # Record timing
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        self.stats["timings"]["last_segment_ms"] = elapsed_ms
        
        # Accumulative timings (when benchmark enabled)
        if self.enable_benchmark:
            self.stats["timings"]["total_ms"] += elapsed_ms
            self.stats["timings"]["segments"] += 1
        
        return result
    
    def _audit_xml_output(self, tree):
        counts, examples = {}, {}
        for element in tree.iter():
            values = [element.text or '', element.tail or '']
            if isinstance(element.tag, str):
                values += list(element.attrib.values())
            for value in values:
                if value.startswith(('urn:', 'http://www.w3.org/', 'http://schemas.', 'http://www.lisa.org/')):
                    continue
                check = self._validate_no_critical_pii(value)
                for cat, count in check['counts'].items():
                    if count: counts[cat] = counts.get(cat, 0) + count
                for cat, vals in check['examples'].items():
                    examples[cat] = list(dict.fromkeys(examples.get(cat, []) + vals))[:3]
        self.stats['critical_pii_remaining'] = {'counts': counts, 'examples': examples} if counts else {}
        self.stats['coverage'] = 'review_required' if counts else 'text_scanned'

    def _is_inline_tag(self, element) -> bool:
        local_name = etree.QName(element.tag).localname if isinstance(element.tag, str) else None
        return local_name in INLINE_TAG_NAMES if local_name else False
    
    def _process_segment_element(self, element, lang: str = "en", **kwargs):
        rewrite_element(element, lambda text: self.process_text_node(text, lang=lang, **kwargs))
    
    def _remove_segment_history(self, tree) -> int:
        """Remove segment version history from MQXLIFF to prevent data leakage.
        
        Removes:
        - <mq:historical-unit> elements (contain old segment versions)
        - Empty <mq:minorversions> elements after cleanup
        - Updates mq:hashistory to "false" for consistency
        
        Returns count of removed elements.
        """
        removed_count = 0
        
        historical_units = tree.xpath("//mq:historical-unit", namespaces=XLIFF_NS)
        for hu in historical_units:
            parent = hu.getparent()
            if parent is not None:
                parent.remove(hu)
                removed_count += 1
        
        # Keep empty mq:minorversions elements - MemoQ requires them for RowHistory
        
        if removed_count > 0:
            mq_ns = XLIFF_NS.get("mq", "MQXliff")
            docinfo_elements = tree.xpath("//mq:docinformation", namespaces=XLIFF_NS)
            for docinfo in docinfo_elements:
                hashistory_attr = f"{{{mq_ns}}}hashistory"
                if hashistory_attr in docinfo.attrib:
                    docinfo.attrib[hashistory_attr] = "false"
        
        return removed_count
    
    def _strip_metadata_mqxliff(self, tree) -> int:
        """Sanitize sensitive metadata from MQXLIFF to prevent data leakage.
        
        Conservative approach: never delete attributes or elements.
        Only replaces values to preserve memoQ compatibility.
        
        Sanitizes:
        - 'original' attribute in <file> → 'document'
        - Username attributes → 'Anonymized'
        - <mq:originalsource> content → copy of anonymized <source>
        - <mq:insertedmatch> source/target → copy of anonymized content
        - <mq:commitinfos> username → 'Anonymized'
        - <mq:export-path> text → cleared
        - <mq:docinformation> children with user paths → text cleared
        
        Returns count of sanitized items.
        """
        from copy import deepcopy
        sanitized = 0
        mq_ns = XLIFF_NS.get("mq", "MQXliff")
        
        username_attrs = {"translatorcommitusername", "lastchanginguser",
                          "creator", "modifier", "creatoruser"}
        
        for file_el in tree.xpath("//xliff:file", namespaces=XLIFF_NS):
            if "original" in file_el.attrib:
                file_el.attrib["original"] = "document"
                sanitized += 1
        
        for tu in tree.xpath("//xliff:trans-unit", namespaces=XLIFF_NS):
            for attr in list(tu.attrib.keys()):
                attr_local = (attr.split("}")[-1] if "}" in attr else attr).lower()
                if attr_local in username_attrs:
                    tu.attrib[attr] = "Anonymized"
                    sanitized += 1
            
            source_el = tu.find("xliff:source", namespaces=XLIFF_NS)
            target_el = tu.find("xliff:target", namespaces=XLIFF_NS)
            
            for osrc in tu.xpath(".//mq:originalsource", namespaces=XLIFF_NS):
                if source_el is not None:
                    osrc.text = source_el.text
                    for child in list(osrc):
                        osrc.remove(child)
                    for child in source_el:
                        osrc.append(deepcopy(child))
                    if "edited" in osrc.attrib:
                        osrc.attrib["edited"] = "false"
                sanitized += 1
            
            for im in tu.xpath(".//mq:insertedmatch", namespaces=XLIFF_NS):
                if "source" in im.attrib:
                    im.attrib["source"] = ""
                for im_src in im.findall("xliff:source", namespaces=XLIFF_NS):
                    if source_el is not None:
                        im_src.text = source_el.text
                        for child in list(im_src):
                            im_src.remove(child)
                        for child in source_el:
                            im_src.append(deepcopy(child))
                for im_tgt in im.findall("xliff:target", namespaces=XLIFF_NS):
                    if target_el is not None:
                        im_tgt.text = target_el.text
                        for child in list(im_tgt):
                            im_tgt.remove(child)
                        for child in target_el:
                            im_tgt.append(deepcopy(child))
                sanitized += 1
            
            for ci in tu.xpath(".//mq:commitinfos", namespaces=XLIFF_NS):
                for commit in list(ci):
                    if "username" in commit.attrib:
                        commit.attrib["username"] = "Anonymized"
                        sanitized += 1
        
        for export_path in tree.xpath("//mq:export-path", namespaces=XLIFF_NS):
            export_path.text = ""
            sanitized += 1
        
        for docinfo in tree.xpath("//mq:docinformation", namespaces=XLIFF_NS):
            for attr in list(docinfo.attrib.keys()):
                attr_local = (attr.split("}")[-1] if "}" in attr else attr).lower()
                if attr_local == "docname":
                    docinfo.attrib[attr] = "document"
                    sanitized += 1
                elif attr_local == "origfile" or "path" in attr_local:
                    docinfo.attrib[attr] = ""
                    sanitized += 1
                elif attr_local in username_attrs:
                    docinfo.attrib[attr] = "Anonymized"
                    sanitized += 1
        
        for mvi in tree.xpath("//mq:docinformation//mq:minorversioninfo", namespaces=XLIFF_NS):
            for attr in list(mvi.attrib.keys()):
                attr_local = (attr.split("}")[-1] if "}" in attr else attr).lower()
                if attr_local in username_attrs:
                    mvi.attrib[attr] = "Anonymized"
                    sanitized += 1
        
        import re
        for details in tree.xpath("//mq:docinformation//mq:details", namespaces=XLIFF_NS):
            if details.text:
                details.text = re.sub(
                    r'<(FilePath|TargetPath)>[^<]*</(FilePath|TargetPath)>',
                    r'<\1></\2>',
                    details.text
                )
                sanitized += 1
        
        for node in tree.xpath("//*[local-name()='note' or local-name()='alt-trans'] | //comment() | //processing-instruction()"):
            if node.getparent() is not None:
                node.getparent().remove(node)
                sanitized += 1
        return sanitized

    def _strip_metadata_tmx(self, tree) -> int:
        """Remove sensitive metadata from TMX to prevent data leakage.
        
        Strips:
        - creationid, changeid, creationdate, changedate, lastusagedate from <tu> and <tuv>
        - creationtool, creationtoolversion, creationid from <header>
        - <prop> and <note> elements inside <tu>
        
        Returns count of stripped items.
        """
        stripped = 0
        
        sensitive_attrs = {
            "creationid", "changeid", "creationdate", "changedate", "lastusagedate",
        }
        
        for tu in tree.xpath("//tu"):
            for attr in list(tu.attrib.keys()):
                if attr.lower() in sensitive_attrs:
                    del tu.attrib[attr]
                    stripped += 1
            
            for tuv in tu.xpath("tuv"):
                for attr in list(tuv.attrib.keys()):
                    if attr.lower() in sensitive_attrs:
                        del tuv.attrib[attr]
                        stripped += 1
            
            for prop in tu.xpath("prop"):
                prop.getparent().remove(prop)
                stripped += 1
            for note in tu.xpath("note"):
                note.getparent().remove(note)
                stripped += 1
        
        for node in tree.xpath('//tuv/prop | //tuv/note | //comment() | //processing-instruction()'):
            if node.getparent() is not None:
                node.getparent().remove(node)
                stripped += 1
        for header in tree.xpath("//header"):
            header.set('creationtool', 'Clean&QA')
            header.set('creationtoolversion', '6.6')
            for key, value in {'adminlang':'en', 'o-tmf':'CleanQA', 'segtype':'sentence', 'datatype':'plaintext'}.items():
                if not header.get(key): header.set(key, value)
            for attr in list(header.attrib.keys()):
                if attr.lower() in sensitive_attrs:
                    del header.attrib[attr]
                    stripped += 1
            for prop in header.xpath("prop"):
                prop.getparent().remove(prop)
                stripped += 1
            for note in header.xpath("note"):
                note.getparent().remove(note)
                stripped += 1
        
        return stripped

    @document_scope
    def anonymize_mqxliff(self, xml_content: bytes, 
                          process_source: bool = True,
                          process_target: bool = True,
                          use_safe_regex: bool = True,
                          use_regex: bool = True,
                          use_proper_names: bool = False,
                          use_dictionary: bool = True,
                          dictionary_terms: Set[str] = None,
                          whitelist_terms: Set[str] = None,
                          progress_callback=None) -> Tuple[bytes, Dict[str, int], List[Dict]]:
        self.reset_stats()
        previews = []
        
        try:
            xml_content = self._normalize_xml_input(xml_content)
            parser = safe_parser()
            tree = parse_xml(xml_content)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Error parsing MQXLIFF: {str(e)}")
        
        from document_core import XLIFF_URI, MAX_SEGMENTS
        if local_name(tree) != 'xliff' or etree.QName(tree).namespace != XLIFF_URI or tree.get('version', '1.2') != '1.2':
            raise ValueError('Only MQXLIFF / XLIFF 1.2 is supported.')
        trans_units = tree.xpath("//xliff:trans-unit", namespaces=XLIFF_NS)
        if not trans_units or len(trans_units) > MAX_SEGMENTS:
            raise ValueError('No supported segments found, or segment limit exceeded.')
        pairs = {(f.get('source-language'), f.get('target-language')) for f in tree.xpath('//xliff:file', namespaces=XLIFF_NS)}
        if len(pairs) > 1:
            raise ValueError('Mixed language pairs in a single MQXLIFF are not supported.')
        self._active_whitelist = whitelist_terms or set()
        if use_regex:
            self._scan_document_for_lowercase(tree)
        
        # Read source/target language from the <file> element instead of
        # hardcoding ``en``/``es``. The download pass already did this; the
        # preview pass did not, so previews of EN→DE / EN→FR / etc. ran the
        # language-sensitive layers with the wrong language and showed a
        # different result from the downloaded file.
        mq_source_lang, mq_target_lang = "en", "es"
        files = tree.xpath("//xliff:file", namespaces=XLIFF_NS)
        if files:
            mq_source_lang = (files[0].get("source-language") or "en")[:2].lower()
            mq_target_lang = (files[0].get("target-language") or "es")[:2].lower()
        
        process_kwargs = {
            "use_safe_regex": use_safe_regex,
            "use_regex": use_regex,
            "use_proper_names": use_proper_names,
            "use_dictionary": use_dictionary,
            "dictionary_terms": dictionary_terms,
            "whitelist_terms": whitelist_terms
        }
        
        original_sources = {}
        original_targets = {}
        
        total_units = len(trans_units)
        for i, tu in enumerate(trans_units):
            if progress_callback and total_units > 0:
                progress_callback(i, total_units)
            source_before = ""
            target_before = ""
            source_after = ""
            target_after = ""
            
            sources = tu.xpath("xliff:source", namespaces=XLIFF_NS)
            targets = tu.xpath("xliff:target", namespaces=XLIFF_NS)
            
            if sources and process_source:
                source = sources[0]
                source_before = self._get_element_text_content(source)
                original_sources[i] = source_before
                self._process_segment_element(source, lang=mq_source_lang, **process_kwargs)
                source_after = self._get_element_text_content(source)
            
            if targets and process_target:
                target = targets[0]
                target_before = self._get_element_text_content(target)
                original_targets[i] = target_before
                self._process_segment_element(target, lang=mq_target_lang, **process_kwargs)
                target_after = self._get_element_text_content(target)
            
            changed = source_before != source_after or target_before != target_after
            previews.append({
                "segment": i + 1,
                "source_before": source_before,
                "source_after": source_after,
                "target_before": target_before,
                "target_after": target_after,
                "changed": changed
            })
        if progress_callback and total_units > 0:
            progress_callback(total_units, total_units)
        
        if whitelist_terms:
            wl_lower = {t.lower() for t in whitelist_terms}
            self.terms_cache -= wl_lower
        
        if (use_regex or use_proper_names) and self.terms_cache:
            self._build_cache_regex()
            for i, tu in enumerate(trans_units):
                if process_source:
                    sources = tu.xpath("xliff:source", namespaces=XLIFF_NS)
                    if sources:
                        source = sources[0]
                        text_before_pass2 = self._get_element_text_content(source)
                        self._apply_cache_to_element(source)
                        text_after_pass2 = self._get_element_text_content(source)
                        if text_before_pass2 != text_after_pass2 and i in original_sources:
                            existing = previews[i] if i < len(previews) else None
                            if existing:
                                existing["source_after"] = text_after_pass2
                                existing["changed"] = True
                            else:
                                previews.append({
                                    "segment": i + 1,
                                    "source_before": original_sources[i],
                                    "source_after": text_after_pass2,
                                    "target_before": original_targets.get(i, ""),
                                    "target_after": self._get_element_text_content(
                                        tu.xpath("xliff:target", namespaces=XLIFF_NS)[0]
                                    ) if tu.xpath("xliff:target", namespaces=XLIFF_NS) else "",
                                    "changed": True
                                })
                
                if process_target:
                    targets = tu.xpath("xliff:target", namespaces=XLIFF_NS)
                    if targets:
                        target = targets[0]
                        text_before_pass2 = self._get_element_text_content(target)
                        self._apply_cache_to_element(target)
                        text_after_pass2 = self._get_element_text_content(target)
                        if text_before_pass2 != text_after_pass2:
                            existing = previews[i] if i < len(previews) else None
                            if existing:
                                existing["target_after"] = text_after_pass2
                                existing["changed"] = True
                            else:
                                previews.append({
                                    "segment": i + 1,
                                    "source_before": original_sources.get(i, ""),
                                    "source_after": self._get_element_text_content(
                                        tu.xpath("xliff:source", namespaces=XLIFF_NS)[0]
                                    ) if tu.xpath("xliff:source", namespaces=XLIFF_NS) else "",
                                    "target_before": original_targets.get(i, ""),
                                    "target_after": text_after_pass2,
                                    "changed": True
                                })
            
            previews.sort(key=lambda p: p["segment"])
        
        history_removed = self._remove_segment_history(tree)
        if history_removed > 0:
            self.stats["history_removed"] = history_removed
        
        metadata_stripped = self._strip_metadata_mqxliff(tree)
        if metadata_stripped > 0:
            self.stats["metadata_stripped"] = metadata_stripped
        
        self._clean_xml_tree(tree)
        self._audit_xml_output(tree)
        result_xml = etree.tostring(tree, xml_declaration=True, encoding="UTF-8")
        
        result_xml = self._normalize_xml_format(result_xml)
        
        return result_xml, self.stats.copy(), previews
    
    def _normalize_xml_format(self, xml_bytes: bytes) -> bytes:
        """Normalize XML format for memoQ compatibility.
        
        Fixes lxml serialization quirks:
        - Uses double quotes in XML declaration
        - Restores space before /> in self-closing tags
        - Preserves version attribute position in xliff element
        """
        import re
        
        result = xml_bytes.replace(
            b"<?xml version='1.0' encoding='UTF-8'?>",
            b'<?xml version="1.0" encoding="UTF-8"?>'
        )
        
        result = re.sub(b'([^ "\'])/>', rb'\1 />', result)
        
        result = re.sub(
            b'<xliff xmlns="([^"]+)" xmlns:mq="([^"]+)" xmlns:xsi="([^"]+)" version="([^"]+)" xsi:schemaLocation="([^"]+)">',
            rb'<xliff version="\4" xmlns="\1" xmlns:mq="\2" xmlns:xsi="\3" xsi:schemaLocation="\5">',
            result
        )
        
        return result
    
    def _get_element_text_content(self, element) -> str:
        return visible_text(element)

    def _normalize_xml_input(self, xml_content: bytes) -> bytes:
        return normalize_xml(xml_content)

    def _clean_xml_tree(self, tree):
        _ctrl_re = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
        for element in tree.iter():
            if element.text and _ctrl_re.search(element.text):
                element.text = _ctrl_re.sub('', element.text)
            if element.tail and _ctrl_re.search(element.tail):
                element.tail = _ctrl_re.sub('', element.tail)

    def _scan_document_for_lowercase_tmx(self, tree):
        trans_units = tree.xpath("//tu")
        
        email_url_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|'
            r'https?://[^\s]+|'
            r'www\.[^\s]+|'
            r'[a-zA-Z0-9.-]+\.(com|org|net|edu|gov|io|co|es|de|fr|uk|eu)[^\s]*',
            re.IGNORECASE
        )
        
        for tu in trans_units:
            for tuv in tu.xpath("tuv"):
                for seg in tuv.xpath("seg"):
                    text = "".join(seg.itertext())
                    if text:
                        clean_text = email_url_pattern.sub(' ', text)
                        words = re.findall(r'\b[a-záéíóúñüàèìòùäëïöü]+\b', clean_text, re.IGNORECASE)
                        for word in words:
                            if word.islower() and len(word) > 2:
                                self.lowercase_words.add(word.lower())

    def _get_tmx_tuv_by_lang(self, tu, lang_code):
        return tmx_variant(tu, lang_code)

    def _detect_tmx_languages(self, tree):
        return tmx_languages(tree)

    @document_scope
    def anonymize_tmx(self, xml_content: bytes,
                      process_source: bool = True,
                      process_target: bool = True,
                      source_lang: str = "en",
                      target_lang: str = "es",
                      use_safe_regex: bool = True,
                      use_regex: bool = True,
                      use_proper_names: bool = False,
                      use_dictionary: bool = True,
                      dictionary_terms: Set[str] = None,
                      whitelist_terms: Set[str] = None,
                      progress_callback=None) -> Tuple[bytes, Dict[str, int], List[Dict]]:
        self.reset_stats()
        previews = []
        
        try:
            xml_content = self._normalize_xml_input(xml_content)
            parser = safe_parser()
            tree = parse_xml(xml_content)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Error parsing TMX: {str(e)}")
        
        trans_units = tree.xpath("//tu")
        
        from document_core import MAX_SEGMENTS
        if local_name(tree) != 'tmx' or not trans_units or len(trans_units) > MAX_SEGMENTS:
            raise ValueError('No supported TMX segments found, or segment limit exceeded.')
        self._active_whitelist = whitelist_terms or set()
        detected_src, detected_tgt = self._detect_tmx_languages(tree)
        if detected_src:
            source_lang = detected_src
        if detected_tgt:
            target_lang = detected_tgt
        src_proc_lang = (source_lang or "en").split("-")[0][:2].lower()
        tgt_proc_lang = (target_lang or "es").split("-")[0][:2].lower()
        
        if use_regex:
            self._scan_document_for_lowercase_tmx(tree)
        
        process_kwargs = {
            "use_safe_regex": use_safe_regex,
            "use_regex": use_regex,
            "use_proper_names": use_proper_names,
            "use_dictionary": use_dictionary,
            "dictionary_terms": dictionary_terms,
            "whitelist_terms": whitelist_terms
        }
        
        original_sources = {}
        original_targets = {}
        
        total_units = len(trans_units)
        for i, tu in enumerate(trans_units):
            if progress_callback and total_units > 0:
                progress_callback(i, total_units)
            source_before = ""
            target_before = ""
            source_after = ""
            target_after = ""
            
            source_seg = self._get_tmx_tuv_by_lang(tu, source_lang)
            target_seg = self._get_tmx_tuv_by_lang(tu, target_lang)
            
            if source_seg is not None and process_source:
                source_before = self._get_element_text_content(source_seg)
                original_sources[i] = source_before
                self._process_segment_element(source_seg, lang=src_proc_lang, **process_kwargs)
                source_after = self._get_element_text_content(source_seg)
            
            if target_seg is not None and process_target:
                target_before = self._get_element_text_content(target_seg)
                original_targets[i] = target_before
                self._process_segment_element(target_seg, lang=tgt_proc_lang, **process_kwargs)
                target_after = self._get_element_text_content(target_seg)
            
            changed = source_before != source_after or target_before != target_after
            previews.append({
                "segment": i + 1,
                "source_before": source_before,
                "source_after": source_after,
                "target_before": target_before,
                "target_after": target_after,
                "changed": changed
            })
        if progress_callback and total_units > 0:
            progress_callback(total_units, total_units)
        
        if whitelist_terms:
            wl_lower = {t.lower() for t in whitelist_terms}
            self.terms_cache -= wl_lower
        
        if (use_regex or use_proper_names) and self.terms_cache:
            self._build_cache_regex()
            for i, tu in enumerate(trans_units):
                if process_source:
                    source_seg = self._get_tmx_tuv_by_lang(tu, source_lang)
                    if source_seg is not None:
                        text_before_pass2 = self._get_element_text_content(source_seg)
                        self._apply_cache_to_element(source_seg)
                        text_after_pass2 = self._get_element_text_content(source_seg)
                        if text_before_pass2 != text_after_pass2 and i in original_sources:
                            existing = previews[i] if i < len(previews) else None
                            if existing:
                                existing["source_after"] = text_after_pass2
                                existing["changed"] = True
                            else:
                                target_seg = self._get_tmx_tuv_by_lang(tu, target_lang)
                                previews.append({
                                    "segment": i + 1,
                                    "source_before": original_sources[i],
                                    "source_after": text_after_pass2,
                                    "target_before": original_targets.get(i, ""),
                                    "target_after": self._get_element_text_content(target_seg) if target_seg is not None else "",
                                    "changed": True
                                })
                
                if process_target:
                    target_seg = self._get_tmx_tuv_by_lang(tu, target_lang)
                    if target_seg is not None:
                        text_before_pass2 = self._get_element_text_content(target_seg)
                        self._apply_cache_to_element(target_seg)
                        text_after_pass2 = self._get_element_text_content(target_seg)
                        if text_before_pass2 != text_after_pass2:
                            existing = previews[i] if i < len(previews) else None
                            if existing:
                                existing["target_after"] = text_after_pass2
                                existing["changed"] = True
                            else:
                                source_seg = self._get_tmx_tuv_by_lang(tu, source_lang)
                                previews.append({
                                    "segment": i + 1,
                                    "source_before": original_sources.get(i, ""),
                                    "source_after": self._get_element_text_content(source_seg) if source_seg is not None else "",
                                    "target_before": original_targets.get(i, ""),
                                    "target_after": text_after_pass2,
                                    "changed": True
                                })
            
            previews.sort(key=lambda p: p["segment"])
        
        metadata_stripped = self._strip_metadata_tmx(tree)
        if metadata_stripped > 0:
            self.stats["metadata_stripped"] = metadata_stripped
        
        self._clean_xml_tree(tree)
        self._audit_xml_output(tree)
        result_xml = etree.tostring(tree, xml_declaration=True, encoding="UTF-8")
        
        result_xml = result_xml.replace(
            b"<?xml version='1.0' encoding='UTF-8'?>",
            b'<?xml version="1.0" encoding="UTF-8"?>'
        )
        
        return result_xml, self.stats.copy(), previews

    # ------------------------------------------------------------------
    # Word (.docx) monolingual anonymization
    # ------------------------------------------------------------------

    _DOCX_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    _DOCX_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"

    def _docx_nearest_wp(self, el):
        """Nearest ancestor <w:p> of an element (or None)."""
        p_tag = f"{{{self._DOCX_W_NS}}}p"
        parent = el.getparent()
        while parent is not None:
            if parent.tag == p_tag:
                return parent
            parent = parent.getparent()
        return None

    def _docx_in_fallback(self, el):
        """True when the element lives inside <mc:Fallback> (duplicated
        legacy copy of a textbox — the <mc:Choice> copy is the live one)."""
        fb_tag = f"{{{self._DOCX_MC_NS}}}Fallback"
        parent = el.getparent()
        while parent is not None:
            if parent.tag == fb_tag:
                return True
            parent = parent.getparent()
        return False

    def _docx_paragraph_chunks(self, p_element):
        """Split a <w:p> into chunks of <w:t> elements between tab/br/cr.

        Only <w:t> whose *nearest* ancestor <w:p> is this paragraph are
        collected (textbox paragraphs nested inside a run's drawing are
        walked on their own, not glued into the host paragraph).
        Returns a list of lists of <w:t> lxml elements.
        """
        w = self._DOCX_W_NS
        t_tag = f"{{{w}}}t"
        break_tags = {f"{{{w}}}tab", f"{{{w}}}br", f"{{{w}}}cr"}
        chunks = []
        current = []
        for el in p_element.iter():
            if el is p_element or not isinstance(el.tag, str):
                continue
            if el.tag == t_tag:
                if self._docx_nearest_wp(el) is p_element:
                    current.append(el)
            elif el.tag in break_tags:
                if self._docx_nearest_wp(el) is p_element and current:
                    chunks.append(current)
                    current = []
        if current:
            chunks.append(current)
        return chunks

    def _docx_redistribute(self, t_elements, original: str, new_text: str):
        """Write ``new_text`` back across the chunk's <w:t> elements.

        Equal spans keep their original <w:t> (preserving run formatting);
        replaced/inserted spans go to the <w:t> containing the span start.
        Guarantees ``"".join(texts) == new_text`` by construction, with a
        defensive fallback to first-element assignment.
        """
        import bisect
        import difflib

        starts = []
        pos = 0
        for t in t_elements:
            starts.append(pos)
            pos += len(t.text or "")

        n = len(t_elements)
        out = [""] * n

        def bucket(offset):
            k = bisect.bisect_right(starts, offset) - 1
            return max(0, min(k, n - 1))

        sm = difflib.SequenceMatcher(None, original, new_text, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(bucket(i1), n):
                    span_start = starts[k]
                    span_end = starts[k + 1] if k + 1 < n else len(original)
                    ov1 = max(i1, span_start)
                    ov2 = min(i2, span_end)
                    if ov1 < ov2:
                        out[k] += new_text[j1 + (ov1 - i1):j1 + (ov2 - i1)]
                    if span_end >= i2:
                        break
            elif tag in ("replace", "insert"):
                out[bucket(i1)] += new_text[j1:j2]
            # delete: drop the span

        if "".join(out) != new_text:
            out = [new_text] + [""] * (n - 1)

        xml_space = "{http://www.w3.org/XML/1998/namespace}space"
        for t, text in zip(t_elements, out):
            t.text = text
            if text != text.strip():
                t.set(xml_space, "preserve")

    @document_scope
    def anonymize_docx(self, docx_bytes: bytes, lang: str = 'es',
                       use_safe_regex=True, use_regex=True, use_proper_names=False,
                       use_dictionary=True, dictionary_terms=None, whitelist_terms=None,
                       progress_callback=None):
        import io, zipfile
        self.reset_stats()
        self._active_whitelist = whitelist_terms or set()
        kwargs = dict(lang=lang, use_safe_regex=use_safe_regex, use_regex=use_regex,
                      use_proper_names=use_proper_names, use_dictionary=use_dictionary,
                      dictionary_terms=dictionary_terms, whitelist_terms=whitelist_terms)
        parts, trees, previews, pending = {}, {}, [], []
        warnings = []
        with checked_zip(docx_bytes) as archive:
            if 'word/document.xml' not in archive.namelist():
                raise ValueError('Not a supported Word DOCX document.')
            for item in archive.infolist():
                name = item.filename
                data = archive.read(name)
                parts[name] = data
                if name.startswith(('word/media/', 'word/embeddings/')):
                    warnings.append('Images / embedded objects are not text-anonymized; inspect them before sharing.')
                if name.startswith('customXml/'):
                    warnings.append('Custom XML data is present; inspect it before sharing.')
                if not name.endswith(('.xml', '.rels')):
                    continue
                root = parse_xml(data)
                trees[name] = root
                if name.startswith('word/') and name.endswith('.xml'):
                    if any(local_name(el) == 't' and etree.QName(el).namespace != W_NS for el in root.iter() if isinstance(el.tag, str)):
                        warnings.append('Drawing / chart text uses an unsupported text representation; inspect it before sharing.')
                    for p, slots in word_paragraphs(root):
                        before = ''.join(e.text or '' for e, _ in slots)
                        if not before.strip(): continue
                        after = self.process_text_node(before, **kwargs)
                        pending.append((slots, before, after, name))
                    for el in root.iter():
                        if not isinstance(el.tag, str): continue
                        for attr in list(el.attrib):
                            alocal = attr.split('}')[-1].lower()
                            if alocal in {'author','initials'}:
                                el.set(attr, 'Anonymized')
                            elif alocal in {'date', 'dateutc'}:
                                del el.attrib[attr]
                            elif alocal in {'descr','title'}:
                                el.set(attr, self.process_text_node(el.get(attr), **kwargs))
                elif name.startswith('docProps/'):
                    # Remove user-entered descriptive properties, retaining structural app properties.
                    for el in list(root):
                        if local_name(el) in {'creator','lastModifiedBy','title','subject','description','keywords','category','contentStatus','created','modified'} or name.endswith('custom.xml'):
                            root.remove(el)
                if name.endswith('.rels'):
                    for rel in root:
                        if rel.get('TargetMode') == 'External':
                            rel.set('Target', 'about:blank')
        if whitelist_terms:
            self.terms_cache -= {t.lower() for t in whitelist_terms}
        for idx, (slots, before, after, name) in enumerate(pending, 1):
            if (use_regex or use_proper_names) and self.terms_cache:
                protected, mapping = self._protect_whitelist_terms(after, whitelist_terms or set())
                after = self._restore_whitelist_placeholders(self._apply_cache(protected), mapping)
            rewrite_slots(slots, before, after)
            previews.append(dict(segment=idx, source_before='', source_after='', target_before=before,
                                 target_after=after, changed=before != after, location=name))
            if progress_callback: progress_callback(idx, len(pending))
        # Deleted-text and field instructions are included. Parts not understood are disclosed.
        residual = {}
        for name, root in trees.items():
            if name.startswith(('word/', 'docProps/', 'customXml/')):
                self._audit_xml_output(root)
                check = self.stats.get('critical_pii_remaining', {})
                if check: residual[name] = check
            parts[name] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        self.stats['critical_pii_remaining'] = residual
        self.stats['coverage_warnings'] = sorted(set(warnings))
        self.stats['coverage'] = 'review_required' if residual or warnings else 'text_scanned'
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in parts.items(): archive.writestr(name, data)
        return output.getvalue(), self.stats.copy(), previews


def _strip_control_chars(text: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def load_dictionary_terms(file_content: str) -> Set[str]:
    file_content = _strip_control_chars(file_content)
    terms = set()
    for line in file_content.strip().split('\n'):
        if ',' in line:
            for part in line.split(','):
                term = part.strip()
                if term:
                    terms.add(term)
        else:
            term = line.strip()
            if term:
                terms.add(term)
    return terms
