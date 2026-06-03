import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, relationship

from database import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("name", name="uq_projects_name"),
        CheckConstraint("trim(name) <> ''", name="ck_projects_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]

    project_access: Mapped[list["ProjectAccess"]] = relationship("ProjectAccess", back_populates="project_ref", cascade="all, delete-orphan")
    conversation_threads: Mapped[list["ConversationThread"]] = relationship("ConversationThread", back_populates="project_ref", cascade="all, delete-orphan")
    prompt_chains: Mapped[list["PromptChain"]] = relationship("PromptChain", back_populates="project_ref", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roles_name"),
        CheckConstraint("trim(name) <> ''", name="ck_roles_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]

    users: Mapped[list["User"]] = relationship("User", back_populates="role_ref")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint("trim(username) <> ''", name="ck_users_username_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    username: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    password_hash_encrypted: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    role_id: Mapped[int] = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)  # type: ignore[assignment]
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)  # type: ignore[assignment]
    password_changed_at: Mapped[datetime.datetime | None] = Column(DateTime(timezone=True), nullable=True)  # type: ignore[assignment]

    role_ref: Mapped["Role"] = relationship("Role", back_populates="users")
    project_access: Mapped[list["ProjectAccess"]] = relationship("ProjectAccess", back_populates="user", cascade="all, delete-orphan")
    created_threads: Mapped[list["ConversationThread"]] = relationship("ConversationThread", foreign_keys="ConversationThread.created_by_id", back_populates="created_by_ref")
    created_messages: Mapped[list["ConversationMessage"]] = relationship("ConversationMessage", foreign_keys="ConversationMessage.created_by_id", back_populates="created_by_ref")
    created_prompt_chains: Mapped[list["PromptChain"]] = relationship("PromptChain", foreign_keys="PromptChain.created_by_id", back_populates="created_by_ref")
    updated_prompt_chains: Mapped[list["PromptChain"]] = relationship("PromptChain", foreign_keys="PromptChain.updated_by_id", back_populates="updated_by_ref")
    created_prompt_chain_versions: Mapped[list["PromptChainVersion"]] = relationship("PromptChainVersion", foreign_keys="PromptChainVersion.created_by_id", back_populates="created_by_ref")

    @property
    def role(self) -> str:
        return self.role_ref.name


class ProjectAccess(Base):
    __tablename__ = "project_access"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_project_access_user_project_id"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # type: ignore[assignment]
    project_id: Mapped[int] = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]

    user: Mapped["User"] = relationship("User", back_populates="project_access")
    project_ref: Mapped["Project"] = relationship("Project", back_populates="project_access")

    @property
    def project(self) -> str:
        return self.project_ref.name


class CacheRequest(Base):
    __tablename__ = "cache_requests"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_cache_requests_cache_key"),
        CheckConstraint("trim(cache_key) <> ''", name="ck_cache_requests_cache_key_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    cache_key: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    payload: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    lru: Mapped[int] = Column(BigInteger, nullable=False, default=0)  # type: ignore[assignment]


class GlobalConfig(Base):
    __tablename__ = "global_config"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)  # Optional: for admin UI context


class ConversationThread(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    project_id: Mapped[int] = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)  # type: ignore[assignment]
    title: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    source: Mapped[str] = Column(String, nullable=False, default="manual")  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    updated_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]

    project_ref: Mapped["Project"] = relationship("Project", back_populates="conversation_threads")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_threads")
    messages: Mapped[list["ConversationMessage"]] = relationship("ConversationMessage", back_populates="thread_ref", cascade="all, delete-orphan")
    imports: Mapped[list["ConversationImport"]] = relationship("ConversationImport", back_populates="thread_ref", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "seq_no", name="uq_conversation_message_thread_seq"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    thread_id: Mapped[int] = Column(Integer, ForeignKey("conversation_threads.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]
    seq_no: Mapped[int] = Column(Integer, nullable=False)  # type: ignore[assignment]
    role: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    content: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    metadata_json: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]

    thread_ref: Mapped["ConversationThread"] = relationship("ConversationThread", back_populates="messages")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_messages")


class ConversationImport(Base):
    __tablename__ = "conversation_imports"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    thread_id: Mapped[int] = Column(Integer, ForeignKey("conversation_threads.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]
    import_format: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    status: Mapped[str] = Column(String, nullable=False, default="pending", index=True)  # type: ignore[assignment]
    raw_payload: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    error_message: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    completed_at: Mapped[datetime.datetime | None] = Column(DateTime(timezone=True), nullable=True)  # type: ignore[assignment]

    thread_ref: Mapped["ConversationThread"] = relationship("ConversationThread", back_populates="imports")


class PromptChain(Base):
    __tablename__ = "prompt_chains"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_prompt_chains_project_name"),
        CheckConstraint("trim(name) <> ''", name="ck_prompt_chains_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    project_id: Mapped[int] = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    description: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    updated_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]
    updated_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]

    project_ref: Mapped["Project"] = relationship("Project", back_populates="prompt_chains")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_prompt_chains")
    updated_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_id], back_populates="updated_prompt_chains")
    versions: Mapped[list["PromptChainVersion"]] = relationship("PromptChainVersion", back_populates="chain_ref", cascade="all, delete-orphan")


class PromptChainVersion(Base):
    __tablename__ = "prompt_chain_versions"
    __table_args__ = (
        UniqueConstraint("chain_id", "version_no", name="uq_prompt_chain_versions_chain_version"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    chain_id: Mapped[int] = Column(Integer, ForeignKey("prompt_chains.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]
    version_no: Mapped[int] = Column(Integer, nullable=False)  # type: ignore[assignment]
    content: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    notes: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]

    chain_ref: Mapped["PromptChain"] = relationship("PromptChain", back_populates="versions")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_prompt_chain_versions")
