import { russianToSan } from '../russianNotation';

describe('russianToSan', () => {
  it('reads Cyrillic piece letters and files, captures and castling', () => {
    expect(russianToSan('1.е4 е5 2.Кф3 Кс6 3.Сс4 Сс5 4.с3 Кф6 5.д4 е:д4 6.с:д4 Сб4+ 7.Кс3 0-0')).toBe(
      '1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d4 exd4 6.cxd4 Bb4+ 7.Nc3 O-O',
    );
    expect(russianToSan('1.e4 e5 2.Фh5 Кc6 3.Сc4 Кf6 4.Ф:f7#')).toBe('1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#');
    expect(russianToSan('1. е4 с5 2. Кф3 д6 3. д4 с:д4 4. К:д4')).toBe('1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4');
  });

  it('leaves words, FENs and links alone', () => {
    expect(russianToSan('Привет, разбери партию')).toBe('Привет, разбери партию');
    const fen = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
    expect(russianToSan(fen)).toBe(fen);
    expect(russianToSan('https://lichess.org/kAdOQKeh')).toBe('https://lichess.org/kAdOQKeh');
  });
});
