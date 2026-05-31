from django.db import models


class Xodim(models.Model):
    user_id = models.BigIntegerField(primary_key=True)
    ism = models.TextField(null=True, blank=True)
    lavozim = models.TextField(null=True, blank=True)
    kod = models.TextField(null=True, blank=True)
    filial = models.TextField(null=True, blank=True)
    telefon1 = models.TextField(null=True, blank=True)
    telefon2 = models.TextField(null=True, blank=True)
    tugilgan_kun = models.TextField(null=True, blank=True)
    topic_id = models.IntegerField(null=True, blank=True)
    status = models.TextField(default="pending")
    sana = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "xodimlar"
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def __str__(self):
        return f"{self.ism} ({self.lavozim})"


class Xabar(models.Model):
    user_id = models.BigIntegerField()
    xodim_name = models.TextField(null=True, blank=True)
    filial = models.TextField(null=True, blank=True)
    xabar_turi = models.TextField(null=True, blank=True)
    vaqt = models.TextField(null=True, blank=True)
    holat = models.TextField(default="kutilmoqda")
    javob_vaqt = models.TextField(null=True, blank=True)
    msg_id = models.IntegerField(null=True, blank=True)
    group_fwd_id = models.IntegerField(null=True, blank=True)
    group_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "xabarlar"
        verbose_name = "Xabar"
        verbose_name_plural = "Xabarlar"

    def __str__(self):
        return f"{self.xodim_name} — {self.xabar_turi} ({self.holat})"


class XabarGuruhi(models.Model):
    user_id = models.BigIntegerField()
    ism = models.TextField(null=True, blank=True)
    filial = models.TextField(null=True, blank=True)
    topic_id = models.IntegerField(null=True, blank=True)
    holat = models.TextField(default="kutilmoqda")
    vaqt = models.TextField(null=True, blank=True)
    javob_vaqt = models.TextField(null=True, blank=True)
    urgency = models.TextField(default="oddiy", null=True, blank=True)

    class Meta:
        db_table = "xabar_guruhi"
        verbose_name = "Xabar guruhi"
        verbose_name_plural = "Xabar guruhlari"

    def __str__(self):
        return f"{self.ism} — {self.holat} ({self.vaqt})"


class FaqKategoriya(models.Model):
    emoji = models.TextField(default="📌")
    nomi = models.TextField()
    tartib = models.IntegerField(default=0)

    class Meta:
        db_table = "faq_kategoriya"
        ordering = ["tartib", "id"]
        verbose_name = "FAQ Kategoriya"
        verbose_name_plural = "FAQ Kategoriyalar"

    def __str__(self):
        return f"{self.emoji} {self.nomi}"


class Faq(models.Model):
    kategoriya = models.ForeignKey(
        FaqKategoriya,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_constraint=False,
    )
    savol = models.TextField()
    javob = models.TextField()
    tartib = models.IntegerField(default=0)

    class Meta:
        db_table = "faq"
        ordering = ["tartib", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQlar"

    def __str__(self):
        return self.savol[:80]


class Baholash(models.Model):
    group_id = models.IntegerField(unique=True)
    checker_id = models.BigIntegerField()
    agent_id = models.BigIntegerField()
    yulduz = models.IntegerField()
    vaqt = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "baholash"
        verbose_name = "Baholash"
        verbose_name_plural = "Baholashlar"

    def __str__(self):
        return f"Guruh {self.group_id}: {self.yulduz}⭐"


class CheckerFaollik(models.Model):
    checker_id = models.BigIntegerField(primary_key=True)
    last_active = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "checker_faollik"
        verbose_name = "Checker faollik"
        verbose_name_plural = "Checker faolliklar"


class Biriktirish(models.Model):
    agent_id = models.BigIntegerField(primary_key=True)
    checker_id = models.BigIntegerField()

    class Meta:
        db_table = "biriktirish"
        verbose_name = "Biriktirish"
        verbose_name_plural = "Biriktirishlar"


class AdminMsgMap(models.Model):
    user_id = models.BigIntegerField()
    group_msg_id = models.IntegerField()
    private_msg_id = models.IntegerField()

    class Meta:
        db_table = "admin_msg_map"
        verbose_name = "Admin xabar mapping"
        verbose_name_plural = "Admin xabar mappinglar"


class Klient(models.Model):
    rasm_file_id = models.TextField(null=True, blank=True)
    firma_nomi = models.TextField()
    telefon1 = models.TextField()
    telefon2 = models.TextField(null=True, blank=True)
    inn = models.TextField(null=True, blank=True, unique=True)
    orienter = models.TextField()
    lokatsiya_lat = models.FloatField(null=True, blank=True)
    lokatsiya_lon = models.FloatField(null=True, blank=True)
    kategoriya = models.TextField()
    dokon_turi = models.TextField()
    distributor = models.TextField()
    agent_kod = models.TextField()
    vizit_kun = models.TextField()
    chastota = models.TextField()
    limit_summa = models.FloatField()
    brendlar = models.TextField(null=True, blank=True)
    status = models.TextField(default="pending")
    reject_reason = models.TextField(null=True, blank=True)
    sana = models.TextField(null=True, blank=True)
    supervisor_id = models.BigIntegerField()
    lokatsiya_address = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "klientlar"
        verbose_name = "Klient"
        verbose_name_plural = "Klientlar"

    def __str__(self):
        return f"{self.firma_nomi} ({self.status})"

    def as_tuple(self) -> tuple:
        return (
            self.id, self.rasm_file_id, self.firma_nomi, self.telefon1,
            self.telefon2, self.inn, self.orienter, self.lokatsiya_lat,
            self.lokatsiya_lon, self.kategoriya, self.dokon_turi, self.distributor,
            self.agent_kod, self.vizit_kun, self.chastota, self.limit_summa,
            self.brendlar, self.status, self.reject_reason, self.sana,
            self.supervisor_id, self.lokatsiya_address,
        )


class Sorov(models.Model):
    agent_id = models.BigIntegerField()
    agent_ism = models.TextField()
    tur = models.TextField()
    dokon_nomi = models.TextField(null=True, blank=True)
    yangi_qiymat = models.TextField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    foto_ids = models.TextField(null=True, blank=True)
    izoh = models.TextField(null=True, blank=True)
    status = models.TextField(default="pending_supervisor")
    supervisor_id = models.BigIntegerField(null=True, blank=True)
    sup_msg_id = models.IntegerField(null=True, blank=True)
    admin_msg_id = models.IntegerField(null=True, blank=True)
    sana = models.TextField()
    group_id = models.IntegerField(null=True, blank=True)
    agent_msg_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "sorovlar"
        verbose_name = "So'rov"
        verbose_name_plural = "So'rovlar"

    def __str__(self):
        return f"#{self.id} {self.agent_ism} — {self.tur} ({self.status})"

    def as_tuple(self) -> tuple:
        return (
            self.id, self.agent_id, self.agent_ism, self.tur, self.dokon_nomi,
            self.yangi_qiymat, self.lat, self.lon, self.foto_ids, self.izoh,
            self.status, self.supervisor_id, self.sup_msg_id, self.admin_msg_id,
            self.sana, self.group_id,
        )


class SupervisorGroup(models.Model):
    supervisor_id = models.BigIntegerField(primary_key=True)
    group_chat_id = models.BigIntegerField()

    class Meta:
        db_table = "supervisor_group"
        verbose_name = "Supervisor guruh"
        verbose_name_plural = "Supervisor guruhlar"


class AdminUser(models.Model):
    user_id = models.BigIntegerField(primary_key=True)

    class Meta:
        db_table = "admins"
        verbose_name = "Admin"
        verbose_name_plural = "Adminlar"

    def __str__(self):
        return str(self.user_id)


class AuditLog(models.Model):
    user_id = models.BigIntegerField(null=True, blank=True)
    user_role = models.CharField(max_length=50, null=True, blank=True)
    action_type = models.CharField(max_length=100, null=True, blank=True)
    target = models.TextField(null=True, blank=True)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, null=True, blank=True)
    request_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-id"]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit loglar"

    def __str__(self):
        return f"{self.action_type} by {self.user_id} at {self.created_at}"


class Instruksiya(models.Model):
    lavozim = models.TextField(primary_key=True)
    matn = models.TextField(null=True, blank=True)
    media_type = models.TextField(null=True, blank=True)
    media_file_id = models.TextField(null=True, blank=True)
    updated_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "instruksiyalar"
        verbose_name = "Instruksiya"
        verbose_name_plural = "Instruksiyalar"

    def __str__(self):
        return self.lavozim
