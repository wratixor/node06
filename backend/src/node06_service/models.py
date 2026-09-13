from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, func

metadata = MetaData()

schema_metadata = Table(
    "schema_metadata",
    metadata,
    # This intentionally contains only a bootstrap marker. Domain tables begin in P02.
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
