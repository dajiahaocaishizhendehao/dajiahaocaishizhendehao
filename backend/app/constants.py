"""领域枚举常量。

独立于 ORM，便于在不加载数据库依赖的情况下测试业务规则。
"""

from __future__ import annotations

import enum


class IpType(str, enum.Enum):
    PATENT = "patent"
    COPYRIGHT = "copyright"
    TRADEMARK = "trademark"


class AssetStatus(str, enum.Enum):
    """知识产权综合状态。专业状态仍保存在各专业表，不做经验性映射。"""

    IN_PROGRESS = "in_progress"  # 办理中
    GRANTED = "granted"  # 已取得权利（授权 / 登记 / 注册）
    INVALID = "invalid"  # 已失效
    OTHER = "other"


class PatentType(str, enum.Enum):
    INVENTION = "invention"
    UTILITY = "utility"
    DESIGN = "design"


class MarkType(str, enum.Enum):
    WORD = "word"
    FIGURATIVE = "figurative"
    COMBINED = "combined"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    IP_ADMIN = "ip_admin"
    USER = "user"


class PartyType(str, enum.Enum):
    COMPANY = "company"
    PERSON = "person"
    ORGANIZATION = "organization"


class PersonType(str, enum.Enum):
    INVENTOR = "inventor"
    DESIGNER = "designer"
    DEVELOPER = "developer"
    CONTACT = "contact"


class MaterialFlag(str, enum.Enum):
    NORMAL = "normal"
    FINAL = "final"
    ORIGINAL_SCAN = "original_scan"


class ExtractionStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CertificateType(str, enum.Enum):
    PATENT = "patent_certificate"
    COPYRIGHT = "copyright_certificate"
    TRADEMARK = "trademark_certificate"


class ElectronicCertStatus(str, enum.Enum):
    ARCHIVED = "archived"
    PENDING = "pending"
    MISSING = "missing"


class PaperCertStatus(str, enum.Enum):
    NOT_RECEIVED = "not_received"
    IN_STORAGE = "in_storage"
    BORROWED = "borrowed"
    TRANSFERRED = "transferred"
    LOST = "lost"


class DateType(str, enum.Enum):
    PLANNED = "planned"
    DUE = "due"
    ACTUAL = "actual"
    CUSTOM = "custom"


class DateSource(str, enum.Enum):
    MANUAL = "manual"
    IMPORTED = "imported"
    RULE = "rule"


class DateStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"


class FeeType(str, enum.Enum):
    AGENCY = "agency"
    APPLICATION = "application"
    SUBSTANTIVE = "substantive"
    ANNUITY = "annuity"
    REGISTRATION = "registration"
    MATERIAL = "material"
    OTHER = "other"


class FeeStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    CANCELED = "canceled"


class ReimbursementStatus(str, enum.Enum):
    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    DONE = "done"


class InvoiceOriginalStatus(str, enum.Enum):
    IN_STORAGE = "in_storage"
    ELECTRONIC = "electronic"
    BORROWED = "borrowed"
    MISSING = "missing"
