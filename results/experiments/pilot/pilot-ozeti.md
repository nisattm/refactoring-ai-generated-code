# Hafta 5 — Pilot özeti (W8)

Hazırlayan: Işıl · Tarih: 21 Kasım 2026 · Kaynak: `results/experiments/pilot/runs.csv` ve her koşunun `run.json` dosyası

**Başlangıç kodu:** `ce03f54`, yani modül 1–14 ve 6.449 SLOC. Baseline: `results/baseline/trial/pilot-ce03f54-v2`.
**Ayarlar:** Model `claude-sonnet-5-5`, effort `high`, Claude Code 2.1.308. Testler: feedback 282, held-out 239.

## 1. Koşular

| | pilot-s01 | pilot-s01b | pilot-s02 | pilot-i01 | scale-s01 |
|---|---|---|---|---|---|
| Yaklaşım | Single | Single | Single | Iterative | Single (son kod, sayılmaz) |
| Koşan / hesap | Işıl / exp-1 | Işıl / exp-1 | Işıl / exp-1 | Fatima / exp-2 | Sıla / exp-3 ⁴ |
| **Sonuç** | **geçersiz** | **no_improvement** | **success** | **success** | **success** |
| Neden | Docker Desktop açılmamıştı, Claude çağrılmadı | koku sayısı 83 → 84 (eşik 1) | — | `REFACTORING_DONE`, gerileme yok | 5 metriğin hepsi iyileşti |
| Çağrı / kod turu | 1 / 0 | 1 / 1 | 1 / 1 | 2 / 2 (2 kabul, 0 red) | 1 / 1 |
| Claude süresi | 0,2 s | 545 s | 263 s | 497 s (427 + 70) | 494 s |
| Ölçüm süresi | — | 270 s | 248 s | 1.251 s ¹ | 1.478 s (24,6 dk) |
| Toplam süre | 2 s | 817 s (13,6 dk) | 513 s (8,6 dk) | 1.754 s (29 dk) | 1.973 s (33 dk) |
| Pencere ² (başlangıç → bitiş) | %3 | %4 → %26 | %4 → %14 | %8 → %30 | %7 → %26 |
| Çıktı tokenı | 0 | 92.660 | 43.715 | 86.215 | 72.757 |
| Önbellekten okuma / yazma | 0 | 12,83 M / 268 K | 4,53 M / 164 K | 10,84 M / 265 K | 8,95 M / 241 K |
| Maliyet (liste fiyatı, $) | 0 | 3,28 | 1,55 | 3,01 | 2,59 |
| Okunan / değiştirilen dosya | 0 / 0 | 78 / 50 | 42 / 31 | 82 / 55 | 92 / 73 |
| Araç çağrıları (Read/Edit/Write) | — | 85 / 127 / 19 | 50 / 116 / 3 | 91 / 243 / 4 | 99 / 234 / 2 |
| Alt ajan / izin reddi | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Gerileme (feedback / held-out) | — | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| API değişikliği | — | yok | yok | yok | yok |
| Feedback metni (en fazla satır) | — | — (Single) | — (Single) | 0 ³ | — (Single) |

¹ Iterative'de her turdan sonra feedback ölçümü yapılıyor (218 s ve 221 s). Sonunda en iyi tur ve 1. tur tam ölçülüyor (393 s ve 419 s).
² Değerler, her çağrının sonundaki `rate_limit_event` satırındaki `five_hour.utilization` değeri. s01b ve s02 için claude.ai Usage sayfası koşudan hemen sonra %28 ve %15 gösterdi; aradaki fark muhtemelen aynı hesaptan yapılan sohbet kullanımı.
³ Hiçbir turda bozulan test olmadığı için modele feedback gitmedi. 2. turun promptunda sadece "Your previous changes were kept." cümlesi vardı.
⁴ scale-s01: son kod (`v0-ai-baseline`, 30.260 SLOC), 22 Kasım 01:33–02:06. Değerler kayıttan (`run.json`, `runs.csv`; PR #155). Pencere: `window_pct_start` 7, çağrı sonundaki `five_hour.utilization` 0,26.

## 2. Metrikler (başlangıç → en iyi tur)

| Metrik | Başlangıç | s01b | s02 | i01 (r1 → r2) |
|---|---|---|---|---|
| Ortalama CC | 2,6795 | 2,4070 ✅ | 2,5676 ✅ | 2,5311 → 2,4634 ✅ |
| Ortalama Cognitive | 1,8578 | 1,5644 ✅ | 1,7258 ✅ | 1,7262 → 1,6524 ✅ |
| MI (ağırlıklı) | 45,8653 | 49,5393 ✅ | 47,8434 ✅ | 48,9481 → 49,4185 ✅ |
| Tekrar (%) | 0,809 | 0,5721 ✅ | 0,8112 (aynı, eşik 0,05) | 0,8576 → 0,7377 ✅ |
| Koku sayısı | 83 | **84 ❌** | 81 ✅ | 82 → 82 ✅ |

scale-s01 son kodda koştuğu için başlangıç değerleri farklı: CC 3,0129 → 2,9187, Cognitive 2,1321 → 2,0328, MI 38,2452 → 39,4801, tekrar %2,9526 → %2,0832, koku 360 → 348. Beş metriğin hepsi iyileşti.

**s01b neden başarısız oldu?** Dört metrik belirgin şekilde iyileşti ama koku sayısı 1 arttı. Değişen kokular: S01 Uzun Metot 15 → 13, S07 Ölü Kod 3 → 2, S11 Sihirli Sayı 8 → 7, **S03 Uzun Parametre Listesi 39 → 43**, S23 16 → 17. Model büyük fonksiyonları bölerken çok parametreli küçük fonksiyonlar üretmiş. Single yaklaşımda geri bildirim olmadığı için model bunu fark edip düzeltemedi. Hafta 7 raporu için not edilmeli.

**Aynı görevde büyük fark:** s01b ve s02 aynı kod ve aynı prompt ile çalıştı. Buna rağmen Claude süresi (545 s ve 263 s), pencere harcaması (22 ve 10 puan) ve sonuç farklı çıktı. Bu da her yaklaşımın birden fazla kez tekrarlanması gerektiğini gösteriyor (W7).

## 3. Kurulum ve süreç bulguları

- **Docker kapalıyken başlatma (2 geçersiz başlangıç):** İkisinde de Claude çağrısı 0,2 saniyede "failed to connect to the docker API" hatasıyla bitti ve kota harcanmadı.
  - **pilot-s01** (Işıl, exp-1, 14:23): `calls/call-1/stderr.txt` dosyasında bu hata var, `runs.csv`'de `image_id = unknown`. Koşu geçersiz olarak kayıtta duruyor, pilot-s01b olarak tekrarlandı.
  - **pilot-i01'in ilk denemesi** (Fatima, exp-2, 15:31): Klasör silindi, 15:33'te aynı run-id ile yeniden başlatıldı. Bu deneme `runs.csv`'de yok.
  - W10'a göre geçersiz koşular yaklaşım başına sayılıyor: pilotta Single 1, Iterative 1.
  - #136'dan sonra motor Docker'ı en başta kontrol ediyor. Docker kapalıysa duruyor ve koşu oluşturmuyor.
- **Asıl deneyler için kural (Fatima ve Işıl, 21 Kasım):** Geçersiz bir koşu silinmez; satırı ve klasörü kayıtta kalır. Tekrarı yeni bir run-id ile yapılır (örneğin s03 → s03b). İstatistiklere sadece `valid=true` olan satırlar girer. Aslınur bu kuralı ADR 004 ekine yazacak.
- **`measure_s` hatası:** Single koşuda tek ölçüm 4 kez toplanıyordu (s01b için 1080 s yazıyordu, doğrusu 270 s). #135 ile düzeltildi. s01b ve s02 satırları `run.json`'daki değerlerle düzeltildi (270 s ve 248,2 s).
- **Docker imajı:** Işıl'ın ve Fatima'nın makinelerinde imaj kimliği farklı (`213b05…` ve `952fee…`), çünkü iki makinede ayrı ayrı derlendi. Analizci araçlarının sürümleri iki makinede birebir aynı (`tool_versions.json`).
- **Kurulum kontrolü (flags.md):** Bütün koşularda araç listesi tam beşliydi, alt ajan 0, izin reddi 0, gizli dosya ya da CLAUDE.md yoktu.

## 4. W13 — Claude çalışırken testler yavaşlıyor mu?

Işıl'ın bilgisayarında Docker içinde pilot kodunun feedback testleri ölçüldü (282 test):

| | 1. çalışma | 2. çalışma |
|---|---|---|
| Tek başına (15:48, 15:50) | 132 s | 125 s |
| pilot-s02'nin Claude çağrısı sırasında (19:34, 19:37) | 127 s | 123 s |

**Sonuç: Yavaşlama yok.** Hafta 6'da kilit, Claude çağrısı sırasında bırakılabilir. Fatima bu değişikliği Multi-Agent pilotundan sonra motora ekleyecek; Aslınur ADR 004 ekine yazacak. 2. paralel çalışmanın son 8 saniyesi motorun ölçümünün başlangıcıyla çakıştı; bu çakışma ihmal edilebilir.

Ek ölçüm: Son kodun feedback seti (875 test) tek başına **22 dk 34 s** sürdü. Iterative'de her turdan sonra bu set çalıştığı için asıl deneylerde her tur yaklaşık 22 dakikalık test süresi ekleyecek.

## 5. Ölçek denemesi: asıl deneylerde kota mı, süre mi belirleyici?

Ölçek denemesi (scale-s01) son kodda (4,7 kat büyük) yapıldı. Sonuçlar:

- **Single için pencere sorun değil:** Son kodda bir Single koşu pencerenin yaklaşık **%19**'unu harcadı (%7 → %26). Bu, pilot kodundaki 10–22 puanla aynı aralıkta. Yani kota harcaması kodun boyutuyla orantılı artmıyor. Muhtemel sebep: model kodun tamamını okumuyor, seçtiği dosyalara bakıyor (92 dosya okudu, 73 dosya değiştirdi; pilotta 42–82 okuma). Bu bir yorum, doğrulanmadı. Önceki "47–100+ puan" tahmini yanlış çıktı.
- **Multi-Agent için pencere sorun:** Son kodda Multi-Agent ölçek denemesi (scale-m01, Işıl, exp-1, 22 Kasım; PR #154) %9'da başladı, 1.618,5 saniye sonra pencerenin **%100**'üne ulaşıp limite takıldı (haftalık %49, 13,20 $ liste fiyatı) ve `discarded_limit` olarak atıldı. Yani Single son kodda tek pencereye rahat sığarken Multi-Agent sığmadı. Multi-Agent için hesap/pencere planı ayrıca düşünülmeli (ADR 005).
- **Süreyi ölçüm belirliyor:** Claude 8 dakikada bitti, ölçüm ise **yaklaşık 25 dakika** sürdü. Son kodun feedback seti tek başına 22,5 dakika (bkz. W13).
- **Iterative için tahmin:** Her turdan sonra feedback ölçümü (~22 dk), sonunda da en iyi tur ve 1. tur için tam ölçüm (~25 dk + ~25 dk) yapılıyor. 4 tur yapan bir Iterative koşusu 2 saati geçebilir. Bu, ölçümlerden yapılan bir tahmin, doğrulanmadı.
- **Planlama:** W6'ya göre her koşu pencere %10'un altındayken başlıyor. Bir koşu yaklaşık %20 harcadığı için pencere başına yine bir koşu düşüyor. Ancak hesaplar paralel çalışabilir, yani 3 hesapla aynı anda 3 koşu. Kilit, Claude çağrısı sırasında bırakılırsa (W13) aynı makinede bekleme de azalır. Darboğaz kota değil, ölçüm süresi ve makine sayısı.

## 6. Açık kalanlar

- **scale-s01 dosyaları:** PR #155 ile eklendi; tablodaki değerler kayıttan doğrulandı.
- **flags.md 7. adım (limit kesintisi):** scale-m01 ile kapandı (PR #154): `is_error: true`, `subtype: "success"`, `api_error_status: 429`; motor limiti `api_error_status`'tan yakaladı.
