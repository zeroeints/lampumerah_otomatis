import sys
sys.path.insert(0, '.')
from fuzzy.fuzzy_controller_opt import FuzzyTrafficController

fc = FuzzyTrafficController()
print('=== TEST FUZZY CONTROLLER OPT (2 Input, 9 Rules) ===')
print(f'{"Kendaraan":>10} {"Antrean":>8} {"Skenario":<22} {"Durasi":>7}  Rule')
print('-' * 85)

tests = [
    (5,  3,  'Sedikit + Pendek'),
    (5,  25, 'Sedikit + Panjang'),
    (13, 10, 'Sedang  + Sedang'),
    (13, 30, 'Sedang  + Panjang'),
    (25, 5,  'Padat   + Pendek'),
    (25, 40, 'Padat   + Panjang'),
    (8,  0,  'Rendah  + Kosong'),
    (15, 20, 'Moderat + Moderat'),
    (28, 45, 'Sangat Padat + Sangat Panjang'),
]

for k, q, lbl in tests:
    dur, detail = fc.infer(k, q)
    print(f'{k:>10} {q:>8} {lbl:<22} {dur:>5}s  {detail["rule"]}')

print()
print('Fixed-time baseline = 30s')
print()

# Bandingkan dengan controller lama
from fuzzy.fuzzy_controller import FuzzyTrafficController as FuzzyOld
fc_old = FuzzyOld()
print('=== PERBANDINGAN: Lama (1 input) vs Baru (2 input) ===')
print(f'{"Kendaraan":>10} {"Antrean":>8} {"Lama":>6} {"Baru":>6} {"Selisih":>8}')
print('-' * 50)
for k, q, lbl in tests:
    dur_old, _ = fc_old.infer(k)
    dur_new, _ = fc.infer(k, q)
    diff = dur_new - dur_old
    sign = '+' if diff > 0 else ''
    print(f'{k:>10} {q:>8} {dur_old:>5}s {dur_new:>5}s {sign}{diff:>6}s')
