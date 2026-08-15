# Bulgular — 02 EDA

Pipeline tarafından otomatik üretildi. Her satır bir grafiğin tek cümlelik yorumu.

1. Birim fiyat sürekli değil, ayrık bir fiyat merdiveninde toplanıyor: en sık 8 fiyat noktası (1,091 TL başta olmak üzere) satış satırlarının %72'ini kaplıyor, medyan 1,000 TL ve dağılım sola çarpık (skew -0.93); IQR 1.5× kuralına göre 611 satır (2.4%) aykırı ama brüt cironun yalnızca %0.9'ini oluşturuyor — negatif birim fiyatlı 15 satırın tamamı ise zaten işaretlenmiş anomali kayıtları.
2. İade oranı tutar bazlı %29.0, adet bazlı %31.1 — 8,086 satır (24%) iade kaydı ve tutar oranının adet oranından düşük kalması, iade edilenlerin ortalama olarak satılanlardan daha ucuz ürünler olduğunu gösteriyor.
3. 350 mağazanın en iyi 20'si net cironun %16.4'ini, ilk %20'lik dilim (70 mağaza) %43'ini üretiyor ve cironun yarısı yalnızca 89 mağazadan geliyor — ciro belirgin şekilde yoğunlaşmış, mağaza bazlı tahminlemede bu az sayıda mağaza modelin doğruluğunu belirleyecek.
4. 10 fit içinde ilk üçü (Straight, Flare, Mom) net cironun %57'ini taşıyor; en yüksek cirolu fit Straight (%24.1) ve kuyrukta kalan fitler tek tek %5'in altında.
5. 71 farklı beden kodunun en çok satan 20'si net adedin %79'ini kaplıyor (en yoğun beden 014, 1,499 adet); kuyrukta 14 beden 10 adedin altında kalıyor ve bunların 5 tanesinin net adedi negatif — yani o bedenlerde dönem içinde satılandan fazlası iade edilmiş, beden bazlı kalıp uyumu için doğrudan bir sinyal.
6. Satış günün 09:00–23:59 aralığına sıkışmış; zirve saat 17:00 (net cironun %12.3'i) ve en yoğun üç saat (16:00, 17:00, 18:00) tek başına %36 pay tutuyor.

## 03 — Zaman ekseni (12 aylık gözlem)

Tek 12 aylık döngü. Mevsimsellik iddiası içermez.

1. 12 aylık gözlemde net ciro 2024-05 (0.57M TL) ile 2024-09 (2.76M TL) arasında 4.8 kat değişiyor; iade oranı ise %22–%43 bandında kalıp ciroyla birlikte savrulmuyor, yani aylık dalgalanma iade davranışından değil satış hacminden geliyor.
2. Brüt satış ile iade tutarı aylık bazda 0.86 korelasyonla birlikte hareket ediyor — iade, kendi başına bir dönemsel olay değil satış hacminin gecikmeli gölgesi gibi davranıyor; bu yüzden net ciroyu modellerken iadeyi ayrı bir seri olarak değil satışın fonksiyonu olarak ele almak daha doğru olacak.
3. Aylık net ciro ortalamadan −%61 ile +%86 arasında sapıyor (değişim katsayısı 0.44) ve yılın ikinci yarısı ilk yarısının 2.0 katı; ancak veride her takvim ayının yalnızca TEK gözlemi olduğu için bu sapmaların mevsimsel mi, kampanya kaynaklı mı yoksa büyüme kaynaklı mı olduğu AYRIŞTIRILAMAZ — mevsimsellik iddiası için en az 24-36 aylık geçmiş, tercihen aynı ayın yıllar arası karşılaştırması gerekir.
4. Haftanın en güçlü günü Pazar (net 3.85M TL), en zayıfı Pazartesi (1.97M TL); hafta sonu iki günde net cironun %42'i dönüyor ve en yoğun tek hücre Pazar 16:00 — mağaza personel planlaması için gün×saat kırılımı ay kırılımından daha aksiyon alınabilir.
5. Fitlerin ay içindeki payı sert biçimde kayıyor: ilk 3 aya kıyasla son 3 ayda Straight +31.6 puan kazanırken Slim Straight -30.3 puan kaybetmiş — ancak bu moda kayması olarak okunamaz, çünkü aynı dönemde koleksiyon devri çok yüksek: satışı olan 249 üründen yalnızca 23'ü (9%) 12 ayın tamamında satılmış, 81'i üç ay veya daha kısa ömürlü; yani fit payındaki değişim tüketici tercihinden mi asortiman kararından mı geliyor bu veriyle ayrıştırılamaz.
6. Ürün devri tahminlemenin önündeki en büyük yapısal engel: 249 üründen 23 tanesinin 12 aylık kesintisiz geçmişi var, dolayısıyla ürün seviyesinde zaman serisi kurulamaz — model fit ve mağaza gibi ürün ömründen bağımsız, kalıcı seviyelerde kurulmalı.
7. Mağaza × ay paneli 4,200 hücreden oluşuyor ve bunların %6.4'inde hiç satış yok; mağaza başına ayda ortalama yalnızca 9 işlem satırı düşüyor — bu seyreklik, mağaza bazlı aylık tahminlemede tek tek mağaza modeli yerine havuzlanmış (hiyerarşik/panel) bir yaklaşımı zorunlu kılıyor.

## 04 — Fit × mağaza potansiyel analizi

Potansiyel tanımı ve skor ağırlıkları: outputs/tables/04_scoring_definition.csv

1. Fit seviyesinde en yüksek potansiyel skoru Straight (80/100): büyüme endeksi +0.62, iade oranı %26, iskonto yoğunluğu %4 ve net cironun %24'i — yani büyümesini iskontoya yaslamadan üretiyor; en düşük skor Boyfriend (20/100).
2. Büyüme × iade matrisinde potansiyel çeyreğine (medyanın üstünde büyüme, altında iade) 2 fit düşüyor: Straight, Baggy — bu çeyrek net cironun %30'ini temsil ediyor, yani büyüme ile iade kalitesini aynı anda tutturan alan cironun azınlığı.
3. En yüksek potansiyelli hücre Straight @ mağaza 1788 (skor 91, büyüme +0.89, iade %7, net 15K TL); ilk 50 hücrenin 27'i Straight fitinden geliyor — potansiyel tek tek mağazalara değil belirli fitlerin mağaza ağına yayılmasına bağlı.
4. En yüksek cirolu 25 mağazada bile fit × mağaza matrisinin yalnızca %89'i eşiği geçiyor; mağaza ortalamasında en yüksek potansiyel Straight, en düşük Skinny — aynı fitin skoru mağazadan mağazaya değiştiği için asortiman kararı fit bazında ülke geneli değil mağaza kümesi bazında verilmeli.
5. İskonto bileşeni doğrulanmamış bir varsayıma dayandığı için skor bu bileşen olmadan da hesaplandı ve sonuç iki katmanlı: genel sıralama sağlam (0.95 Spearman korelasyonu), AMA ilk 20 hücrenin yalnızca 10'si ortak — yani hangi fitin genel olarak iyi olduğu varsayımdan bağımsız, ancak 'en iyi 20 hücre' listesi doğrudan iskonto varsayımına bağlı ve aksiyon alınmadan önce DiscountAmount'ın gerçek tanımı Mavi tarafına teyit ettirilmeli.
