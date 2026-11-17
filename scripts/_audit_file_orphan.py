"""审计：操作失败时文件是否残留。"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import Material
from app.storage import LocalStorage
import tempfile
engine=create_engine('sqlite+pysqlite:///:memory:',poolclass=StaticPool)
Base.metadata.create_all(engine);S=sessionmaker(bind=engine);db=S()
with tempfile.TemporaryDirectory() as td:
 s=LocalStorage(Path(td)); stored=s.save(b'abc',suffix='.pdf')
 print('saved before db:',s.exists(stored.storage_key))
 # 模拟 save 后 DB/识别前异常：当前路由无 try/finally 删除物理文件
 db.rollback()
 print('exists after rollback:',s.exists(stored.storage_key))
db.close();Base.metadata.drop_all(engine);engine.dispose()
