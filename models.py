"""
Ma'lumot modellari — DB tuple laridan nom orqali foydalanish uchun.

Misol:
    row = await db.get_xodim(uid)
    x = Xodim.from_row(row)
    print(x.lavozim)   # row[3] ni eslab qolish shart emas
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Xodim:
    status:   str
    topic_id: Optional[int]
    ism:      str
    lavozim:  str
    filial:   str
    kod:      str

    @classmethod
    def from_row(cls, row: tuple) -> "Xodim":
        return cls(
            status=row[0], topic_id=row[1], ism=row[2],
            lavozim=row[3], filial=row[4], kod=row[5],
        )

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"


@dataclass
class Klient:
    id:               int
    rasm_file_id:     Optional[str]
    firma_nomi:       str
    telefon1:         str
    telefon2:         Optional[str]
    inn:              Optional[str]
    orienter:         str
    lokatsiya_lat:    Optional[float]
    lokatsiya_lon:    Optional[float]
    kategoriya:       str
    dokon_turi:       str
    distributor:      str
    agent_kod:        str
    vizit_kun:        str
    chastota:         str
    limit_summa:      float
    brendlar:         Optional[str]
    status:           str
    reject_reason:    Optional[str]
    sana:             Optional[str]
    supervisor_id:    int
    lokatsiya_address: Optional[str]

    @classmethod
    def from_row(cls, row: tuple) -> "Klient":
        return cls(
            id=row[0], rasm_file_id=row[1], firma_nomi=row[2],
            telefon1=row[3], telefon2=row[4], inn=row[5],
            orienter=row[6], lokatsiya_lat=row[7], lokatsiya_lon=row[8],
            kategoriya=row[9], dokon_turi=row[10], distributor=row[11],
            agent_kod=row[12], vizit_kun=row[13], chastota=row[14],
            limit_summa=row[15], brendlar=row[16], status=row[17],
            reject_reason=row[18], sana=row[19], supervisor_id=row[20],
            lokatsiya_address=row[21] if len(row) > 21 else None,
        )


@dataclass
class Sorov:
    id:            int
    agent_id:      int
    agent_ism:     str
    tur:           str
    dokon_nomi:    Optional[str]
    yangi_qiymat:  Optional[str]
    lat:           Optional[float]
    lon:           Optional[float]
    foto_ids:      Optional[str]
    izoh:          Optional[str]
    status:        str
    supervisor_id: Optional[int]
    sup_msg_id:    Optional[int]
    admin_msg_id:  Optional[int]
    sana:          Optional[str]
    group_id:      Optional[int]

    @classmethod
    def from_row(cls, row: tuple) -> "Sorov":
        return cls(
            id=row[0], agent_id=row[1], agent_ism=row[2],
            tur=row[3], dokon_nomi=row[4], yangi_qiymat=row[5],
            lat=row[6], lon=row[7], foto_ids=row[8], izoh=row[9],
            status=row[10], supervisor_id=row[11], sup_msg_id=row[12],
            admin_msg_id=row[13], sana=row[14],
            group_id=row[15] if len(row) > 15 else None,
        )
