from dataclasses import dataclass
from datetime import datetime
from typing import List
@dataclass
class Stream_Meta:
    __tablename__ = "streaming_meta"
    user_id: int
    stream_id: int
    start_time: datetime
    end_time: datetime
    hls_folder: str



    
    



