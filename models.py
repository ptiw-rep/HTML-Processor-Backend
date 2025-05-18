from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class HTMLData(Base):
    __tablename__ = "html_data"

    token = Column(String, primary_key=True, index=True)
    html = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
