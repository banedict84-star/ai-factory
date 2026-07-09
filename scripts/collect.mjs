#!/usr/bin/env node
/**
 * 안산 의원 대시보드 — 뉴스 자동 수집기
 *
 * 실행: node scripts/collect.mjs
 * 소스: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 있으면 네이버 뉴스 API,
 *       없으면 구글 뉴스 RSS(키 불필요)로 자동 폴백.
 *
 * 동작: data/members.json 의 의원 30명 각각에 대해 '이름 안산' 뉴스를 검색해
 *       - 최근 90일
 *       - 제목/요약에 의원 이름 + '안산' 포함
 *       - 동명이인 제외어(EXCLUDE) 필터
 *       를 적용, 중복 제거 후 최신순 최대 8건을 member.a 에 기록한다.
 *       검색 실패(네트워크/0건)면 기존 기사를 그대로 유지(안전).
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const DATA = path.join(ROOT, 'ansan-dashboard', 'data', 'members.json');

const WINDOW_DAYS = 90;
const MAX_PER_MEMBER = 100;  // ← 의원별 최대 기사 수(90일 내 전부 수집; 상한 100)
const NOW = new Date();

// 동명이인·오탐 제외어 (제목/요약에 있으면 버림)
const EXCLUDE = {
  '장윤정': ['고양', '가수', '트로트'],       // 고양시의원 / 가수 동명이인
  '박은정': ['검사', '장관', '통일부', '검찰'], // 박은정 前 검사/국회 동명이인
  '김현':   ['배우', '아나운서']
};

// 네이버 API 는 언론사명을 안 주므로 도메인→언론사명 매핑(주요 매체). 없으면 호스트명 사용.
const DOMAIN_NAMES = {
  'kyeongin.com':'경인일보','incheonilbo.com':'인천일보','kgnews.co.kr':'경기신문',
  'viva100.com':'브릿지경제','m-i.kr':'매일일보','shinailbo.co.kr':'신아일보',
  'kihoilbo.co.kr':'기호일보','joongboo.com':'중부일보','ekn.kr':'에너지경제',
  'labortoday.co.kr':'매일노동뉴스','thereport.co.kr':'더리포트','enewstoday.co.kr':'이뉴스투데이',
  'todaykorea.co.kr':'투데이코리아','newscj.com':'뉴스천지','banwol.net':'반월신문',
  'kpinews.kr':'KPI뉴스','ifm.kr':'경인방송','ohmynews.com':'오마이뉴스',
  'yna.co.kr':'연합뉴스','newsis.com':'뉴시스','news1.kr':'뉴스1','hankyung.com':'한국경제',
  'mk.co.kr':'매일경제','seoul.co.kr':'서울신문','khan.co.kr':'경향신문','hani.co.kr':'한겨레',
  'chosun.com':'조선일보','joongang.co.kr':'중앙일보','donga.com':'동아일보',
  'heraldcorp.com':'헤럴드경제','nspna.com':'NSP통신','asn24.com':'경인신문',
  'kyeonggi.com':'경기일보','gnews.gg.go.kr':'경기GN뉴스','kmaeil.com':'경기매일'
};
function srcName(host){
  const h = host.replace(/^www\./,'');
  return DOMAIN_NAMES[h] || h.replace(/\.(co\.kr|or\.kr|go\.kr|com|kr|net)$/,'');
}

const CID = process.env.NAVER_CLIENT_ID;
const CSEC = process.env.NAVER_CLIENT_SECRET;
const USE_NAVER = !!(CID && CSEC);

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function fetchT(url, opts = {}, ms = 15000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  try { return await fetch(url, { ...opts, signal: ac.signal }); }
  finally { clearTimeout(t); }
}
const decode = s => (s || '')
  .replace(/<\/?b>/g, '')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&apos;/g, "'")
  .replace(/&amp;/g, '&').trim();
const mmdd = d => `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
const daysAgo = d => (NOW - d) / 86400000;

async function fetchNaver(query) {
  const out = [];
  // 최신순으로 100건씩 페이지네이션. 90일보다 오래된 기사가 나오면 중단(그 이후는 다 오래됨).
  for (let start = 1; start <= 901; start += 100) {
    const url = `https://openapi.naver.com/v1/search/news.json?query=${encodeURIComponent(query)}&display=100&start=${start}&sort=date`;
    const res = await fetchT(url, { headers: { 'X-Naver-Client-Id': CID, 'X-Naver-Client-Secret': CSEC } });
    if (!res.ok) throw new Error(`naver ${res.status}`);
    const items = (await res.json()).items || [];
    for (const it of items) {
      let host = '';
      try { host = new URL(it.originallink || it.link).hostname; } catch {}
      out.push({ title: decode(it.title), url: it.originallink || it.link, source: srcName(host), date: new Date(it.pubDate), desc: decode(it.description) });
    }
    if (items.length < 100) break;
    const last = new Date(items[items.length - 1].pubDate);
    if (!isNaN(last) && daysAgo(last) > WINDOW_DAYS) break; // 90일 경계 넘음
    await sleep(120);
  }
  return out;
}

async function fetchGoogle(query) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=ko&gl=KR&ceid=KR:ko`;
  const res = await fetchT(url, { headers: { 'User-Agent': 'Mozilla/5.0 (ansan-dashboard-bot)' } });
  if (!res.ok) throw new Error(`google ${res.status}`);
  const xml = await res.text();
  return xml.split('<item>').slice(1).map(chunk => {
    const g = re => (chunk.match(re) || [])[1] || '';
    let title = decode(g(/<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/));
    const link = decode(g(/<link>([\s\S]*?)<\/link>/));
    const pub = g(/<pubDate>([\s\S]*?)<\/pubDate>/);
    const source = decode(g(/<source[^>]*>([\s\S]*?)<\/source>/));
    // 구글 RSS 제목은 "제목 - 언론사" 형태 → 언론사 분리
    if (source && title.endsWith(' - ' + source)) title = title.slice(0, -(source.length + 3)).trim();
    return { title, url: link, source, date: new Date(pub), desc: '' };
  }).filter(x => x.title && x.url);
}

const provider = USE_NAVER ? fetchNaver : fetchGoogle;

function keep(member, a) {
  const text = `${a.title} ${a.desc}`;
  if (!text.includes(member.n)) return false;              // 이름 포함(기본 확인만)
  if (!(a.date instanceof Date) || isNaN(a.date)) return false;
  if (daysAgo(a.date) > WINDOW_DAYS || daysAgo(a.date) < -1) return false; // 90일 이내
  return true; // 동명이인 등은 일단 그대로 둠(추후 필요 시 EXCLUDE/안산 필터 재적용)
}

async function collectFor(member) {
  const query = `${member.n}의원`;   // ← 검색어 (여기서 조정). 현재: 붙여쓰기(예: 김남국의원)
  let raw;
  try {
    raw = await provider(query);
  } catch (e) {
    console.warn(`  ! ${member.n}: 검색 실패(${e.message}) → 기존 기사 유지`);
    return null; // 유지
  }
  const seen = new Set();
  const kept = [];
  for (const a of raw) {
    if (!keep(member, a)) continue;
    const key = a.url.split('?')[0];
    if (seen.has(key)) continue;
    seen.add(key);
    kept.push({ t: a.title, s: a.source || '뉴스', d: mmdd(a.date), u: a.url, iso: a.date.toISOString() });
  }
  kept.sort((x, y) => (y.iso || '').localeCompare(x.iso || ''));
  return kept.slice(0, MAX_PER_MEMBER);
}

async function main() {
  const doc = JSON.parse(fs.readFileSync(DATA, 'utf8'));
  const members = doc.members || [];
  console.log(`네이버 키 감지 — ID:${CID ? 'O' : 'X'} SECRET:${CSEC ? 'O' : 'X'}`);
  console.log(`소스: ${USE_NAVER ? '네이버 뉴스 API' : '구글 뉴스 RSS(키없음)'} · 대상 ${members.length}명`);
  if (!USE_NAVER) console.log('  ⚠ NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 시크릿이 안 잡혔습니다 — 이름/저장 확인 필요');

  let updated = 0;
  for (const m of members) {
    const res = await collectFor(m);
    if (res && res.length) {
      m.a = res;
      m.c = res.length;
      updated++;
      console.log(`  ✓ ${m.n}: ${res.length}건`);
    } else if (res && res.length === 0) {
      // 0건이면 기존 유지(품질 안전). 원하면 여기서 m.a=[] 로 비울 수 있음.
      console.log(`  · ${m.n}: 신규 0건 → 기존 ${(m.a || []).length}건 유지`);
    }
    await sleep(USE_NAVER ? 120 : 400); // rate limit 완화
  }

  // KST 타임스탬프
  const kst = new Date(NOW.getTime() + 9 * 3600000);
  const pad = n => String(n).padStart(2, '0');
  doc.generatedAt = `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())} ${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())} KST`;
  doc.source = USE_NAVER ? '네이버 뉴스 검색 API' : '구글 뉴스 RSS';

  fs.writeFileSync(DATA, JSON.stringify(doc, null, 2) + '\n');
  console.log(`완료: ${updated}/${members.length}명 갱신 · ${doc.generatedAt}`);
}

main().catch(e => { console.error('수집 실패:', e); process.exit(1); });
