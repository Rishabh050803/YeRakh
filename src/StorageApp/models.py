from sqlmodel import SQLModel,Field,Column
import sqlalchemy.dialects.postgresql as pg
from datetime import datetime,date
from uuid import UUID,uuid4

class FileModel(SQLModel,table=True):
    __tablename__ = "files"
    uuid:UUID = Field(
        sa_column=Column(
            pg.UUID,
            nullable = False,
            primary_key = True,
            default = uuid4,
        ))
    name:str
    folder_path:str
    size:int
    created_at: datetime = Field(sa_column=Column(
        pg.TIMESTAMP(timezone=True),
        nullable=False,
        default=datetime.now
    ))
   