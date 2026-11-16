# Araç kontrolü (PR 1, issue #104)

Tarih: 2026-11-16/17 · Dal: `analyzer/tool-check` · Komut: `python -I scripts/analyzer/tool_check.py` (imaj `refactoring-env`, ID `11c96c1d6c9f`, Python 3.14.10, `--network none`, repo salt okunur bağlandı).

Her araç, `lms/`'in temiz bir kopyası üzerinde (`__pycache__` yok), proje dışı nötr bir çalışma klasöründe çalıştırıldı. Ham çıktılar commit edilmedi. Ölçülen kod: `main` @ `71e91e3` (246 dosya, 29.019 SLOC).

> **Not (kod boyutu):** 29.019 SLOC, ADR 002'deki "en az 30.000 SLOC" şartının altında. Modül 29 (`printing/`) henüz yok; adım 27'yi ekip tamamlayacak ve eşiğin aşılması bekleniyor. Analizci `printing/` yokken D2'deki "not generated" kuralıyla çalışır. Kesin başlangıç ölçümü (#112) Nisa söyleyince yapılır.

## 1. Araçlar

| Araç | Sürüm | Çıktı biçimi | Süre | Çıkış kodu | Beklenen → işlenen dosya |
| --- | --- | --- | --- | --- | --- |
| Radon raw | 6.0.1 | `-j` JSON, dosya başına | 1,2 sn | 0 | 246 → 246 |
| Radon cc | 6.0.1 | `-j` JSON, blok listesi | 0,8 sn | 0 | **212** → 212 (bkz. §4.1) |
| Radon mi | 6.0.1 | `-j` JSON | 2,5 sn | 0 | 246 → 246 |
| Radon hal | 6.0.1 | `-j -f` JSON (dosya + fonksiyon) | 0,8 sn | 0 | 246 → 246 |
| complexipy | 8.3.0 | Python API `file_complexity()`; `FileComplexity.functions[]` (`name`, `complexity`, `line_start`, `line_end`) | 0,4 sn | – | 246 → 246 |
| Ruff | 0.17.3 | `--output-format json` | 0,1 sn | 1 (bulgu var) | 246 → 246 (`--show-files`) |
| Pylint | 4.1.3 | `--output-format=json2` | **22,7 sn** (`-j 1`) | 8 (bit maskesi: refactor mesajı) | 249 → 249 (= dosya + 3, bkz. §4.3) |
| Vulture | 2.16 | metin satırları | 1,1 sn | 3 (bulgu var) | doğrulanamaz (dosya listesi yok) |
| jscpd | 5.4.2 | `json` raporu (`statistics`, `duplicates`) | 0,14 sn | 0 | 214–215 → 215 (bkz. §4.2) |
| PyExamine | 0.2.3 | `--output x.csv` (+ aynı klasöre `.txt`) | 10,8 sn | **0 (11 dosyada çökmeye rağmen)** | CSV yalnızca bulgusu olan dosyaları listeler |

Toplam: birincil araçlar (Radon, complexipy, Ruff, Pylint, jscpd) ≈ 29 sn; Vulture + PyExamine ile ≈ 40 sn. D16 ("~30 sn") birincil kümede tutuyor; ikincil araçlar dahil ~40 sn.

## 2. Birincil metrikler (mevcut `main`, ön değer; kesin hesap PR 3'te)

| Metrik | Değer | Not |
| --- | --- | --- |
| Ortalama CC | 3,0226 (1.771 birim) · 3,0157 (closure'larla 1.787 birim) | bkz. §4.4 |
| Ortalama Cognitive | 2,1355 (1.771 birim) | |
| MI (SLOC ağırlıklı) | 38,1508 | düz ortalama 54,8777; 43 dosya MI = 100 |
| Tekrar % | 2,8751 (105 klon, 1.049 satır, 36.486 fiziksel satır) | |
| Toplam koku | PR 3'te | S01, S02, S18, S22 ve `cast(` kendi scriptimiz; burada ölçülmedi |

## 3. D8 kuralları: sürümde var mı, pozitif kontrol, LMS bulgusu

Pozitif kontrol: `scripts/tests/fixtures/analyzer/poscontrol/pkg/` (6 dosya). Ruff stabil kurallar tek komutta; `PLR0916` ayrı `--preview` komutunda (bkz. §4.5).

| Koku | Araç / kural | Sürümde var | Pozitif kontrol | LMS bulgusu |
| --- | --- | --- | --- | --- |
| S01 | kendi AST (45 satır) | – | PR 3 | PR 3 |
| S02 | kendi AST (15 metot, `plain`) | – | PR 3 | PR 3 |
| S03 | Ruff PLR0913 | evet | 3 | 182 (52 handler: doğrulanmadı, PR 3) |
| S07 | Ruff F401 + F841 | evet | 1 + 1 | 4 + 0 (`--ignore-noqa`, stabil) |
| S09 | Ruff PLR0916 (`--preview` gerekli) + SIM | evet | 1 + 3 | 1 + 1 (SIM401) |
| S10 | Pylint R1702 (**preview gerekmez**) | evet | 1 | 0 |
| S11 | Ruff PLR2004 | evet | 1 | 42 |
| S18 | kendi import grafiği | – | PR 3 | bkz. §4.6 |
| S19 | Ruff S110 + BLE001 | evet | 1 + 2 | 0 + 0 |
| S20 | Ruff B006 | evet | 1 | 0 |
| S21 | Ruff RET | evet | 3 (RET503 ×2, RET505) | 0 |
| S22 | kendi script | – | PR 3 | PR 3 |
| S23 | Ruff ANN401 + PGH003 + `cast(` | evet | 2 + 1 + (cast PR 3) | **51** + 0 + 0 |
| ikincil | Pylint W0718 / R1710 / W0101 | evet | 2 / 1 / 1 | 0 / 0 / 0 |
| çapraz kontrol | Pylint R0401 | evet | 1 | 24 |
| ikincil | `# noqa` / `# type: ignore` sayısı | – | PR 3 | 38 / 100 (grep) |

Pozitif kontrolde `--ignore-noqa` etkisi görüldü: `# noqa: F401` satırı yalnızca `--ignore-noqa` ile raporlanıyor. `ruff --select S110` yalnızca `except Exception: pass` ve çıplak `except`'i yakalar; `except OSError: pass` S110 değildir (SIM105 olarak çıkar).

Vulture %80: LMS'te 7 bulgu (hepsi `core/money.py` ve `core/timeutil.py`'de SQLAlchemy olay/Pydantic kancalarının kullanılmayan argümanları, yani yanlış alarm; §6 ile aynı).

## 4. Bulgular ve karar bekleyen noktalar

### 4.1 Radon cc boş dosyaları atlar
246 dosyanın 34'ünde (ör. `__init__.py` dosyaları) fonksiyon/sınıf yok; `radon cc` bunları çıktıya koymaz. D13 kontrolü "beklenen" kümesini bu yüzden **en az bir `def`/`class` içeren dosyalar** (AST ile, 212) olarak tanımlar.

### 4.2 jscpd 50 token altındaki dosyaları okumaz
215 dosya okundu. Python tokenizer ile (isim, sayı, string, işleç **+ NEWLINE**) ≥ 50 token olan dosya sayısı da 215; NEWLINE'sız 214 (`core/schemas.py`: 44 anlamlı token, NEWLINE ile 50+). Sınıra yakın başka dosya yok (56 ve 60 token). D13'te jscpd'nin beklenen kümesi bu tokenizer kuralıyla hesaplanır (yaklaşık, "doğrulanmadı": jscpd dosya listesi vermiyor).

### 4.3 Pylint `modulesLinted` = dosya + 3
1, 3, 6 ve 246 dosyalık paketlerde sabit +3 (4, 6, 9, 249). Pylint dosya listesi vermediği için D13 kontrolü `dosya + 3` ile yapılır (deneysel sabit, sürüm değişirse yeniden doğrulanmalı).

### 4.4 İç içe fonksiyonlar: D4 ile D5 aynı birim kümesini vermiyor (**karar gerekli**)
- Radon, closure'ları ayrı blok olarak verir ve ebeveynin CC'sine **eklemez** (denendi: ebeveyn 2, iç fonksiyon 2). LMS'te 16 closure → 1.787 birim.
- complexipy iç fonksiyonu ebeveyne **ekler** (aynı örnekte ebeveyn 3) ve ayrı birim üretmez → 1.771 birim.
- D4 ("iç içe ayrı birim") ile D5 ("aynı birim kümesi") birlikte sağlanamıyor. Fark %0,9 ve ortalamalar 3,0226 / 3,0157.
- **Öneri:** CC ortalaması 1.787 birim (D4 aynen), Cognitive ortalaması 1.771 birim (complexipy'nin birimleri); birleştirme anahtarında closure satırlarının `cognitive` değeri boş; her iki birim sayısı `summary.json`'da raporlanır. Alternatif: ikisini de 1.771 ebeveyn birimde tutmak (closure CC'si ebeveyne eklenir). Karar bekliyor.

### 4.5 Ruff: `--preview` sonuçları değiştiriyor (**karar gerekli**)
- `PLR0916` yalnızca `--preview` ile var (bir kural olarak). Ama `--preview` tüm seçimde açılırsa **F401 4'ten 27'ye çıkıyor** (`core/db.py`'deki 24 model-kaydı importunun 23'ü `# noqa: F401` ile işaretli; preview sürümü bunları kullanılmamış import sayıyor, stabil sürüm yalnızca birini). §6'daki "3'ten 27'ye" bu iki bayrağın karışımı: stabil `--ignore-noqa`'sız 3, stabil `--ignore-noqa` ile 4, preview + `--ignore-noqa` 27.
- Preview açıkken çıktı biçimi `concise` kural kodu yerine kural adı yazıyor (`unused-import`); `json` biçimi her durumda `code` verir. Analizci `json` kullanmalı.
- `--preview` önek seçimlerinin (`SIM`, `RET`) kapsamını da genişletebilir; bu kodda sayılar değişmedi (SIM 1, RET 0), ama stabil kurallar yine de ayrı koşuda tutulur.
- **Öneri:** iki koşu: (1) stabil, `--ignore-noqa`: PLR0913, F401, F841, SIM, PLR2004, S110, BLE001, B006, RET, ANN401, PGH003; (2) `--preview --select PLR0916`. S07 = 4 (+ 0). Preview F401 (27) ikincil sayı olarak raporlanır. Gerekçe: model-kaydı importlarının taşınması S07'yi yapay olarak 23 oynatmasın.

### 4.6 S18 döngü sayısı çok kaba (**bilgi/karar**)
- Dosya düzeyinde SCC (boyut > 1): fonksiyon içi importlar dahil **1 bileşen (25 dosya: `core/db.py` + 24 `models.py`)**; yalnızca modül düzeyi importlar: **0**. Paket düzeyinde modül importlarıyla 25 paketlik tek bileşen var (paketler birbirini içe aktarıyor, `api` hariç).
- Pylint R0401: 24 ayrı "cyclic-import" mesajı (hepsi aynı `core.db` döngüsünün yolları) → sayı olarak S18 ile karışmamalı; ikincil çapraz kontrol.
- **Öneri:** S18 birincil = dosya düzeyi SCC sayısı (dahil: 1, hariç: 0), ikincil olarak "döngülerdeki düğüm sayısı" (25) ve paket düzeyi SCC boyutu raporlanır; böylece bileşenin tümüyle kalkması ile yalnızca küçülmesi ayrı görünür.

### 4.7 PyExamine
- `--config` ile çalışıyor, 0.2.3'te JSON yok (csv/txt). Çıkış kodu 0, ama `detect_middle_man` **11 `schemas.py` dosyasında** `ValueError: max() iterable argument is empty` ile çöküyor (`auth, catalog, digital, donations, events, ill, messaging, preservation, programs, purchasing, suggestions`). Çökme yalnızca stderr'de; analizci `Unexpected error analyzing <dosya>` satırlarını yakalayıp raporlamalı.
- Çıktı satır **sayısı** aynı ama satır **sırası** ve açıklama içindeki küme sıralaması koşudan koşuya değişiyor (3 koşuda 2–4 satır farkı, sadece bu sıralama) → ikincil metrik, sıralayıp normalize etmeden bayt bayt karşılaştırılamaz.
- **Yan etki:** paket `import` edildiğinde (`code_quality_analyzer`) çalışma klasörüne `code_analysis.log` yazıyor; CLI de yazıyor. Analizci yalnızca CLI'yi nötr klasörde çalıştırır, paketi import etmez.
- CSV yalnızca bulgusu olan dosyaları listeler (231/246) ve günlük işlenen dosyaları yazmaz; D13 kontrolü "çöken dosya sayısı = 0" olarak tanımlandı.
- `--config` verilmezse çalışma klasöründeki `code_quality_config.yaml`'ın alındığı `--help` metninde yazıyor; ayrıca denemedim. "Core içeren döngüleri atlıyor" iddiası (§6) **doğrulanmadı** (PR 6).

### 4.8 Belirlenimcilik (iki koşu)
Radon cc: içerik aynı (bayt düzeyinde fark var, anahtar sırası); Pylint: mesaj kümesi aynı, **sıra farklı**; jscpd: aynı (yalnız `detectionDate`); PyExamine: yukarıdaki fark. Analizci tüm ham çıktıları ayrıştırıp sıralamalı (D14).

## 5. Python 3.13 ön ölçümleriyle karşılaştırma

| Konu | 3.13 ön ölçüm | 3.14.10 imajı |
| --- | --- | --- |
| Dosya / SLOC | 246 / 29.019 | aynı |
| Radon birim | 1.771 | aynı (+16 closure ayrı, bkz. §4.4) |
| MI düz / ağırlıklı / MI=100 | 54,88 / 38,15 / 43 | aynı |
| jscpd | %2,88, 105 klon, 215/246 | aynı |
| PLR0913 / PLR2004 | 182 / 42 | aynı |
| F401 | 3 → 27 (`--ignore-noqa`) | 27 yalnızca `--preview` ile; `--ignore-noqa` tek başına 3 → 4 (§4.5) |
| `noqa` / `type: ignore` / `cast(` / PGH003 | 38 / 100 / 0 / 0 | aynı |
| Pylint dört kural / R0401 | 0 / 24 | aynı |
| Vulture %80 | 7 yanlış alarm | aynı |
| PyExamine | 11 dosyada exit-0 çökme | aynı 11 dosya |
| Toplam süre | < 30 sn | birincil ≈ 29 sn, hepsi ≈ 40 sn |
| ANN401 | belirtilmemişti | **51 bulgu** (S23'ün asıl bileşeni) |

Fark yalnızca F401 sayısının nedeni (bayrak karışımı) ve ANN401'in ilk kez görünmesi.

## 6. Dondurulmuş liste önerisi

S01, S02, S03, S07, S09, S10, S11, S18, S19, S20, S21, S22, S23 (D8 aynen). Hepsi sürümde var ve pozitif kontrolü geçti (tool kuralları: pozitif kontrol; kendi scriptler: PR 3'ün fixture testleri). LMS'te sıfır bulgulu kurallar (S10, S19, S20, S21, S23-PGH003/cast) pozitif kontrolü geçtiği için listede kalır. S09'un SIM bileşeni için `SIM` öneki aynen kullanılır (kuralları tek tek yazmak yerine); sürüm değişirse liste değişir, `tool_versions.json` bunu gösterir. İkincil (toplama girmez): Pylint W0718, R1710, W0101, R0401; Vulture; PyExamine; `noqa`/`type: ignore` sayıları; Ruff preview-F401.

## 7. Katman ihlali tanımı önerisi

Kodun yapısı: `lms/core` (en alt), `lms/<paket>/` (models, schemas, rules, service, …; domain), `lms/api` (en üst; 33 dosya). Import yönü beklendiği gibi: `api` hiçbir paket tarafından içe aktarılmıyor (kök `lms/__init__.py` hariç); `core` yalnızca `core/db.py:create_schema` içinde 24 modeli fonksiyon içinde içe aktarıyor.

Öneri, üç kural; hepsi AST ile sayılan import ifadeleri:
1. **API doğrudan kalıcılığa uzanıyor:** `lms/api/**` içinde `lms.<paket>.models` veya `sqlalchemy*` importu. Başlangıç: **34 (models, 19 dosya) + 17 (sqlalchemy, 14 dosya) = 51 ifade, 33 API dosyasının 21'inde.** (`lms.core.db`'den `get_session` gibi bağımlılık enjeksiyonu importları ihlal sayılmaz; 30 dosyada var.)
2. **Alttan üste import:** `core` veya herhangi bir domain paketinin `lms.api`'yi içe aktarması. Başlangıç: 0.
3. **`core` → domain, modül düzeyinde:** Başlangıç: 0 (24 fonksiyon içi import S18'de sayılıyor).

Tek sayı raporlanır (1+2+3), kural başına kırılımla. Bu bir öneri: kural 1 başlangıçta büyük olduğu için refactoring'in en çok oynatacağı sayı o olur; "service katmanı yok" gibi yorumlara girmiyor.

## 8. Doğrulanmadı / sonraki PR'larda

- FastAPI handler sayısının 52 olması (PR 3, AST).
- S01, S02, S18, S22, `cast(` değerleri (PR 3).
- PyExamine'in `core` içeren döngüleri atlaması ve `--config`'siz davranışı (PR 6).
- Pylint `+3` sabiti ve jscpd NEWLINE kuralı yalnızca bu sürümler için doğrulandı.
- Vulture için dosya kapsama kontrolü yapılamıyor (araç dosya listesi vermiyor); ikincil olduğu için sadece "çalıştı, çıkış 0/3" kontrol edilir.
- jscpd şu bayraklarla çalıştırıldı: `--min-lines 5 --min-tokens 50 --pattern '**/*.py' --no-gitignore --reporters json,silent`. Varsayılan `--mode` değeri yardım metninde yazmıyor; açıkça yazmak gerekip gerekmediği PR 2'de ADR'ye girmeden önce bakılacak (doğrulanmadı).

## Yeniden üretme

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network none -v "$(pwd -W):/work:ro" -v "<çıktı klasörü>:/out" refactoring-env bash -c '
  cd /work
  python -I scripts/analyzer/tool_check.py --code dataset/lms/generated --pkg lms --out /out/lms
  python -I scripts/analyzer/tool_check.py --code scripts/tests/fixtures/analyzer/poscontrol --pkg pkg --out /out/control --control'
```
