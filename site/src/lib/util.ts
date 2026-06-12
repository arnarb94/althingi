// grunnslóð vefsins (t.d. /althingi á GitHub Pages), án loka-skástriks
export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
export const url = (p: string) => BASE + p;

export function fmtTime(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h > 0) return `${h} klst ${m} mín`;
  return `${m} mín`;
}

export function pct(x: number | null | undefined): string {
  if (x == null) return '–';
  return `${(x * 100).toFixed(1)}%`;
}

export interface SessionStats {
  lthing: number;
  flokkur_id: number | null;
  flokkur: string | null;
  kjordaemi: string | null;
  tegund: string | null;
  speeches: number;
  seconds: number;
  ja: number;
  nei: number;
  sat_hja: number;
  bodadi_fjarvist: number;
  fjarverandi: number;
  atkvaedi_alls: number;
  maeting: number | null;
  med_flokki: number | null;
}

export interface Member {
  id: number;
  nafn: string;
  faedingardagur: string | null;
  skammstofun: string | null;
  thing: SessionStats[];
}

export function memberTotals(m: Member) {
  const t = {
    speeches: 0, seconds: 0, ja: 0, nei: 0, sat_hja: 0,
    bodadi_fjarvist: 0, fjarverandi: 0, atkvaedi_alls: 0,
  };
  for (const p of m.thing) {
    t.speeches += p.speeches; t.seconds += p.seconds;
    t.ja += p.ja; t.nei += p.nei; t.sat_hja += p.sat_hja;
    t.bodadi_fjarvist += p.bodadi_fjarvist; t.fjarverandi += p.fjarverandi;
    t.atkvaedi_alls += p.atkvaedi_alls;
  }
  const present = t.ja + t.nei + t.sat_hja;
  return { ...t, maeting: t.atkvaedi_alls ? present / t.atkvaedi_alls : null };
}

export function latestSeat(m: Member): SessionStats {
  return m.thing[m.thing.length - 1];
}

export function slug(name: string): string {
  return name
    .toLowerCase()
    .replaceAll('á', 'a').replaceAll('é', 'e').replaceAll('í', 'i')
    .replaceAll('ó', 'o').replaceAll('ú', 'u').replaceAll('ý', 'y')
    .replaceAll('ö', 'o').replaceAll('æ', 'ae').replaceAll('ð', 'd')
    .replaceAll('þ', 'th')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}
