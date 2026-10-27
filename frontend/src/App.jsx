import React, { useState, useEffect, useRef } from 'react';
import {
  Flame, Search, Sparkles, ExternalLink, Star, Download, X,
  TrendingUp, Activity, BarChart2, Radio, Zap, Award,
  ChevronLeft, ChevronRight, Database, Wifi, Send,
  ShieldCheck, AlertTriangle, RefreshCw, Play, Users,
  FileText, ArrowRight, Check,
  Globe, Laptop, Gamepad2, Dumbbell, Coins, Utensils, Compass, BookOpen
} from 'lucide-react';
import './App.css';

/* ══════════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════════ */
function fmt(num) {
  if (!num || isNaN(num)) return '0';
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(2) + 'M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
  return Number(num).toLocaleString();
}

function getInitial(name) {
  return name ? name.trim().charAt(0).toUpperCase() : 'C';
}

function getSparklinePath(points, W = 320, H = 50) {
  if (!points || points.length < 2) return { line: '', area: '' };
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const pts = points.map((v, i) => [
    (i / (points.length - 1)) * W,
    H - ((v - min) / range) * (H - 10) - 5,
  ]);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const cpX = (pts[i - 1][0] + pts[i][0]) / 2;
    d += ` C ${cpX} ${pts[i - 1][1]}, ${cpX} ${pts[i][1]}, ${pts[i][0]} ${pts[i][1]}`;
  }
  return { line: d, area: `${d} L ${W} ${H} L 0 ${H} Z` };
}

const BADGE_COLOR_MAP = { emerald: 'emerald', purple: 'purple', cyan: 'cyan', slate: 'slate' };
const BADGE_ICON_MAP = {
  EXPLODING: <Zap size={10} />,
  'HIGH CONVERSION': <Award size={10} />,
  TRENDING: <TrendingUp size={10} />,
  STEADY: <Activity size={10} />,
};
const CARD_VARIANT_MAP = {
  EXPLODING: 'variant-exploding',
  'HIGH CONVERSION': 'variant-conversion',
  TRENDING: 'variant-trending',
  STEADY: '',
};
const SPARKLINE_COLOR_MAP = {
  EXPLODING: { stroke: '#34d399', fill: '#34d399' },
  'HIGH CONVERSION': { stroke: '#c4b5fd', fill: '#c4b5fd' },
  TRENDING: { stroke: '#7dd3fc', fill: '#7dd3fc' },
  STEADY: { stroke: '#f4a0b5', fill: '#f4a0b5' },
};

/* ══════════════════════════════════════════════════
   ROOT APP
══════════════════════════════════════════════════ */
export default function App() {
  const [mode, setMode] = useState('vault'); // 'vault' | 'live'
  const [stats, setStats] = useState(null);

  const [shortlist, setShortlist] = useState(() => {
    try { return JSON.parse(localStorage.getItem('glow_shortlist') || '[]'); } catch { return []; }
  });
  const [inspectCreator, setInspectCreator] = useState(null);
  const [showShortlist, setShowShortlist] = useState(false);

  useEffect(() => {
    localStorage.setItem('glow_shortlist', JSON.stringify(shortlist));
  }, [shortlist]);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats).catch(() => {});
  }, []);

  const toggleShortlist = (c) =>
    setShortlist(prev =>
      prev.some(x => x.channel_id === c.channel_id)
        ? prev.filter(x => x.channel_id !== c.channel_id)
        : [...prev, c]
    );
  const isStarred = (id) => shortlist.some(c => c.channel_id === id);

  const exportCSV = () => {
    if (!shortlist.length) return;
    const headers = ['channel_id', 'channel_name', 'category', 'size_tier', 'promotion_score', 'subscribers', 'typical_reach', 'promo_lift', 'channel_url'];
    const rows = shortlist.map(c => [c.channel_id, `"${(c.channel_name || '').replace(/"/g, '""')}"`, `"${c.category || ''}"`, c.size_tier, c.promotion_score, c.subscribers, c.typical_reach, c.promo_lift, c.channel_url]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `glowiq_shortlist_${Date.now()}.csv` });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  return (
    <>
      <div className="ambient-bg">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
      </div>

      <div className="app-container">
        {/* ── HEADER ── */}
        <header className="app-header">
          <div className="brand-wrapper" onClick={() => setMode('vault')}>
            <div className="brand-icon">
              <Flame size={20} color="#fff" />
            </div>
            <div className="brand-text">
              <h1>GlowIQ <span className="brand-badge">v2.0</span></h1>
              <p>Beauty Influencer Intelligence</p>
            </div>
          </div>

          {/* ── MODE SWITCHER ── */}
          <div className="mode-switcher">
            <button
              className={`mode-tab ${mode === 'vault' ? 'active' : ''}`}
              onClick={() => setMode('vault')}
            >
              <Database size={15} />
              <span>HDFS Vault</span>
              {stats && <span className="mode-tab-count">{fmt(stats.total_creators)}</span>}
            </button>
            <button
              className={`mode-tab ${mode === 'live' ? 'active live' : ''}`}
              onClick={() => setMode('live')}
            >
              <div className="live-dot" />
              <Wifi size={15} />
              <span>Live Query</span>
              <span className="mode-tab-badge">YouTube API</span>
            </button>
          </div>

          <div className="header-actions">
            <button
              className={shortlist.length > 0 ? 'btn btn-rose' : 'btn btn-ghost'}
              onClick={() => setShowShortlist(true)}
            >
              <Star size={15} fill={shortlist.length > 0 ? '#fff' : 'none'} />
              <span>Shortlist ({shortlist.length})</span>
            </button>
          </div>
        </header>

        {/* ── VIEWS ── */}
        {mode === 'vault' ? (
          <VaultView
            stats={stats}
            isStarred={isStarred}
            onStar={toggleShortlist}
            onInspect={setInspectCreator}
          />
        ) : (
          <LiveView
            isStarred={isStarred}
            onStar={toggleShortlist}
          />
        )}
      </div>

      {/* ── MODALS ── */}
      {inspectCreator && (
        <InspectModal
          creator={inspectCreator}
          starred={isStarred(inspectCreator.channel_id)}
          onStar={toggleShortlist}
          onClose={() => setInspectCreator(null)}
        />
      )}
      {showShortlist && (
        <ShortlistModal
          shortlist={shortlist}
          onRemove={toggleShortlist}
          onExport={exportCSV}
          onClear={() => setShortlist([])}
          onClose={() => setShowShortlist(false)}
        />
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════
   MODE 1 — VAULT VIEW (HDFS Dataset)
══════════════════════════════════════════════════ */
function VaultView({ stats, isStarred, onStar, onInspect }) {
  const [creators, setCreators] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedTrend, setSelectedTrend] = useState('all');
  const [selectedTier, setSelectedTier] = useState('all');
  const [sortBy, setSortBy] = useState('promotion_potential_score');
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetch('/api/categories').then(r => r.json()).then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ page, limit: '18', sort_by: sortBy, sort_order: 'desc' });
    if (search.trim()) p.append('search', search.trim());
    if (selectedCategory !== 'all') p.append('category', selectedCategory);
    if (selectedTrend !== 'all') p.append('trend', selectedTrend);
    if (selectedTier !== 'all') p.append('size_tier', selectedTier);
    fetch(`/api/creators?${p}`)
      .then(r => r.json())
      .then(d => { setCreators(d.items || []); setTotalPages(d.pages || 1); setTotalCount(d.total || 0); setLoading(false); })
      .catch(() => setLoading(false));
  }, [search, selectedCategory, selectedTrend, selectedTier, sortBy, page]);

  const reset = () => { setSearch(''); setSelectedCategory('all'); setSelectedTrend('all'); setSelectedTier('all'); setPage(1); };

  const handleInspect = (channelId) => {
    fetch(`/api/creators/${channelId}`).then(r => r.json()).then(onInspect).catch(() => {});
  };

  return (
    <>
      {/* Hero */}
      <section className="hero-section">
        <div className="hero-eyebrow">
          <Database size={13} />
          <span>Apache Spark ML · HDFS Parquet · Gold Tier</span>
        </div>
        <h2 className="hero-title">
          Discover <em>Exploding</em><br />Beauty Creators
        </h2>
        <p className="hero-subtitle">
          Browse 2,615+ pre-scored skincare, makeup & haircare channels ranked by a 6-factor promotion potential model.
        </p>

        {stats && (
          <div className="stat-chips">
            <div className="stat-chip">
              <div className="stat-chip-dot" style={{ background: '#34d399', boxShadow: '0 0 6px #34d399' }} />
              <span className="stat-chip-val">{fmt(stats.exploding_creators)}</span>
              <span className="stat-chip-label">Exploding</span>
            </div>
            <div className="stat-chip">
              <div className="stat-chip-dot" style={{ background: '#c4b5fd', boxShadow: '0 0 6px #c4b5fd' }} />
              <span className="stat-chip-val">{fmt(stats.high_lift_creators)}</span>
              <span className="stat-chip-label">High Conversion</span>
            </div>
            <div className="stat-chip">
              <div className="stat-chip-dot" style={{ background: '#f4a0b5', boxShadow: '0 0 6px #f4a0b5' }} />
              <span className="stat-chip-val">{stats.average_promotion_score}</span>
              <span className="stat-chip-label">Avg Score</span>
            </div>
            <div className="stat-chip">
              <div className="stat-chip-dot" style={{ background: '#7dd3fc', boxShadow: '0 0 6px #7dd3fc' }} />
              <span className="stat-chip-val">{fmt(stats.total_audience_reach)}</span>
              <span className="stat-chip-label">Total Reach</span>
            </div>
          </div>
        )}

        <div className="search-wrap">
          <div className="search-box">
            <div className="search-icon-wrap"><Search size={18} /></div>
            <input
              type="text"
              className="search-input"
              placeholder="Search by name, category, channel ID — 'skincare', 'James', 'hyaluronic'…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
            {search && <button className="search-clear" onClick={() => setSearch('')}><X size={16} /></button>}
          </div>
        </div>
      </section>

      {/* Category pills */}
      <div className="category-bar">
        {categories.map(cat => (
          <button
            key={cat.id}
            className={`cat-chip ${selectedCategory === cat.id ? 'active' : ''}`}
            onClick={() => { setSelectedCategory(cat.id); setPage(1); }}
          >
            <span>{cat.name}</span>
            <span className="cat-chip-count">{cat.count}</span>
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="controls-bar">
        <div className="ctrl-group">
          <span className="ctrl-label">Trend</span>
          {[
            { id: 'all', label: 'All' },
            { id: 'exploding', label: '🚀 Exploding' },
            { id: 'conversion', label: '💎 Conversion' },
            { id: 'trending', label: '⚡ Trending' },
          ].map(t => (
            <button key={t.id} className={`ctrl-pill ${selectedTrend === t.id ? 'active' : ''}`} onClick={() => { setSelectedTrend(t.id); setPage(1); }}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="ctrl-divider" />
        <div className="ctrl-group">
          <span className="ctrl-label">Tier</span>
          {['all', 'Nano', 'Micro', 'Mid', 'Macro'].map(tier => (
            <button key={tier} className={`ctrl-pill ${selectedTier.toLowerCase() === tier.toLowerCase() ? 'active' : ''}`} onClick={() => { setSelectedTier(tier); setPage(1); }}>
              {tier === 'all' ? 'All' : tier}
            </button>
          ))}
        </div>
        <div className="ctrl-divider" />
        <div className="ctrl-group">
          <span className="ctrl-label">Sort</span>
          <select className="ctrl-select" value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(1); }}>
            <option value="promotion_potential_score">Promo Score</option>
            <option value="subscribers">Subscribers</option>
            <option value="total_views">Total Views</option>
            <option value="promo_lift">Promo Lift</option>
            <option value="engagement_rate">Engagement</option>
          </select>
        </div>
        <span className="ctrl-count">{totalCount.toLocaleString()} channels</span>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="state-center">
          <Activity size={40} className="spin" color="var(--rose)" />
          <p className="state-title">Querying HDFS Data Lake…</p>
          <p className="state-desc">Filtering {fmt(totalCount || 2615)} channels via Spark ML</p>
        </div>
      ) : creators.length === 0 ? (
        <div className="state-center">
          <div className="state-icon">🔍</div>
          <p className="state-title">No creators match your filters</p>
          <p className="state-desc">Try clearing your search or switching category</p>
          <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={reset}>Reset Filters</button>
        </div>
      ) : (
        <div className="cards-grid">
          {creators.map(c => (
            <CreatorCard
              key={c.channel_id}
              creator={c}
              starred={isStarred(c.channel_id)}
              onStar={onStar}
              onInspect={() => handleInspect(c.channel_id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>
            <ChevronLeft size={16} /><span>Prev</span>
          </button>
          <span className="page-indicator">Page <strong>{page}</strong> of <strong>{totalPages}</strong></span>
          <button className="btn btn-ghost" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
            <span>Next</span><ChevronRight size={16} />
          </button>
        </div>
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════
   MODE 2 — LIVE QUERY VIEW (YouTube API)
══════════════════════════════════════════════════ */
/* ══════════════════════════════════════════════════
   MODE 2 — LIVE QUERY VIEW (YouTube API Multi-Domain)
══════════════════════════════════════════════════ */
const DOMAIN_OPTIONS = [
  {
    id: 'auto',
    name: 'All Domains',
    icon: Globe,
    color: 'rose',
    placeholder: "Search any topic or product — e.g. 'M4 MacBook Pro vs Dell XPS', 'Hypertrophy workout routine', 'Artisan sourdough bread'…",
    examples: [
      'M4 MacBook Pro vs Dell XPS comparison',
      'Hypertrophy push pull legs workout split',
      'Beginner artisan sourdough bread loaf',
      'Elden Ring Shadow of the Erdtree boss walkthrough',
      'Korean skincare glass skin routine with niacinamide',
    ],
  },
  {
    id: 'technology',
    name: 'Tech & Gadgets',
    icon: Laptop,
    color: 'lavender',
    placeholder: "Describe your tech gadget or software — e.g. 'Top budget mechanical keyboards with hot swap switches'…",
    examples: [
      'M4 MacBook Pro vs Dell XPS comparison review',
      'Best wireless gaming mouse under $100',
      'Custom mechanical keyboard build sound test',
      'RTX 4090 GPU benchmarks for 4K video editing',
    ],
  },
  {
    id: 'gaming_entertainment',
    name: 'Gaming & Esports',
    icon: Gamepad2,
    color: 'amber',
    placeholder: "Describe your game or gaming topic — e.g. 'Elden Ring boss walkthroughs & speedruns'…",
    examples: [
      'Elden Ring Shadow of the Erdtree boss walkthrough',
      'Competitive Valorant settings and aim routine',
      'Nintendo Switch 2 leaks and hardware analysis',
      'Top 10 cozy indie games on Steam',
    ],
  },
  {
    id: 'fitness_health',
    name: 'Fitness & Health',
    icon: Dumbbell,
    color: 'emerald',
    placeholder: "Describe your fitness regimen or supplement — e.g. 'High protein vegan meal prep for lean bulk'…",
    examples: [
      'Hypertrophy push pull legs workout split',
      'High protein vegan meal prep for lean bulk',
      'Calisthenics muscle up progression for beginners',
      'Zone 2 cardio training for endurance running',
    ],
  },
  {
    id: 'finance_investing',
    name: 'Finance & Crypto',
    icon: Coins,
    color: 'cyan',
    placeholder: "Describe your finance topic or investment — e.g. 'Dividend investing portfolio strategy for passive income'…",
    examples: [
      'Dividend investing portfolio strategy for passive income',
      'Bitcoin cycle top indicators and crypto analysis',
      'Roth IRA index fund portfolio breakdown',
      'Real estate syndication vs REITs for beginners',
    ],
  },
  {
    id: 'beauty_personal_care',
    name: 'Beauty & Skincare',
    icon: Sparkles,
    color: 'rose',
    placeholder: "Describe your beauty product — e.g. 'Ultra-hydrating vitamin-C serum for oily skin with SPF 30'…",
    examples: [
      'Ultra-hydrating vitamin-C serum for oily skin',
      'Korean skincare glass skin routine with snail mucin',
      'Long-wear matte lipstick for dark skin tones',
      'Curly haircare routine for 3C low porosity hair',
    ],
  },
  {
    id: 'food_cooking',
    name: 'Food & Cooking',
    icon: Utensils,
    color: 'coral',
    placeholder: "Describe your recipe or culinary dish — e.g. 'Beginner artisan sourdough bread loaf tutorial'…",
    examples: [
      'Beginner artisan sourdough bread loaf tutorial',
      'Cast iron ribeye steak reverse sear technique',
      'Authentic Japanese ramen broth from scratch',
      'Quick 15-minute high protein dinner recipes',
    ],
  },
  {
    id: 'travel_adventure',
    name: 'Travel & Lifestyle',
    icon: Compass,
    color: 'gold',
    placeholder: "Describe your travel destination or trip — e.g. 'Two weeks backpacking in Japan budget itinerary'…",
    examples: [
      'Two weeks backpacking in Japan budget itinerary',
      'Top hidden gems in Switzerland travel vlog',
      'Digital nomad lifestyle and cost of living in Bali',
    ],
  },
  {
    id: 'education_science',
    name: 'Science & Education',
    icon: BookOpen,
    color: 'lavender',
    placeholder: "Describe your STEM topic or explainer — e.g. 'Machine learning transformer architecture explained intuitively'…",
    examples: [
      'James Webb Space Telescope latest deep field discoveries',
      'Machine learning transformer architecture explained intuitively',
      'Quantum computing qubits and superposition demo',
    ],
  },
];

function LiveView({ isStarred, onStar }) {
  const [selectedDomain, setSelectedDomain] = useState('auto');
  const [query, setQuery] = useState('');
  const [apiMode, setApiMode] = useState('dry_run'); // 'dry_run' | 'live'
  const [confirmed, setConfirmed] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ran, setRan] = useState(false);
  const [statusMsg, setStatusMsg] = useState(null);
  const [quotaInfo, setQuotaInfo] = useState(null);
  const [detectedDomainMeta, setDetectedDomainMeta] = useState(null);
  const textareaRef = useRef(null);

  const activeDomainObj = DOMAIN_OPTIONS.find(d => d.id === selectedDomain) || DOMAIN_OPTIONS[0];

  const canRun = query.trim().length > 3 && !loading && (apiMode === 'dry_run' || (apiMode === 'live' && confirmed));

  const runSearch = () => {
    setLoading(true);
    setStatusMsg(null);
    setResults([]);
    setQuotaInfo(null);
    setDetectedDomainMeta(null);
    fetch('/api/live-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query.trim(),
        domain: selectedDomain,
        mode: apiMode,
        confirmed,
      }),
    })
      .then(async r => {
        const text = await r.text();
        let d = {};
        try { d = JSON.parse(text); } catch { throw new Error(text || `HTTP ${r.status}`); }
        if (!r.ok) throw new Error(d.detail || d.message || `Error ${r.status}`);
        return d;
      })
      .then(d => {
        setLoading(false);
        setRan(true);
        setResults(d.results || []);
        setQuotaInfo(d.quota_status || null);
        setDetectedDomainMeta({
          domain: d.detected_domain,
          name: d.detected_domain_name,
        });
        setStatusMsg({ type: 'success', text: d.message });
      })
      .catch(e => {
        setLoading(false);
        setRan(true);
        setStatusMsg({ type: 'error', text: `${e.message}` });
      });
  };

  const useExample = (brief) => {
    setQuery(brief);
    if (textareaRef.current) textareaRef.current.focus();
  };

  return (
    <div className="live-view">
      {/* ── Live View Hero ── */}
      <section className="live-hero">
        <div className="hero-eyebrow live">
          <div className="live-pulse" />
          <Wifi size={13} />
          <span>YouTube Data API v3 · Multi-Domain Discovery · QuotaGuard Protected</span>
        </div>
        <h2 className="hero-title">
          Discover Creators <em>Live</em><br />Across Any Domain
        </h2>
        <p className="hero-subtitle">
          Query the live YouTube Data API in real time. Search creators across <strong>Tech, Gaming, Fitness, Finance, Food, Beauty, Travel & Science</strong> with automated quota defense.
        </p>
      </section>

      {/* ── Domain Selector Pill Bar ── */}
      <div className="domain-selector-wrapper">
        <div className="domain-selector-header">
          <span className="domain-selector-label">Target Domain:</span>
          <span className="domain-selector-hint">Select a domain or keep on Auto to detect from your query</span>
        </div>
        <div className="domain-selector-pills">
          {DOMAIN_OPTIONS.map(dom => {
            const Icon = dom.icon;
            const isSelected = selectedDomain === dom.id;
            return (
              <button
                key={dom.id}
                className={`domain-pill ${isSelected ? 'active ' + dom.color : ''}`}
                onClick={() => setSelectedDomain(dom.id)}
              >
                <Icon size={14} />
                <span>{dom.name}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Two-panel layout ── */}
      <div className="live-layout">

        {/* LEFT — Query Panel */}
        <div className="live-query-panel">

          {/* Brief input */}
          <div className="live-query-box">
            <div className="live-query-header">
              <FileText size={16} color="var(--rose)" />
              <span>Search Query / Product Brief</span>
              <span className="live-query-domain-tag">
                {activeDomainObj.name}
              </span>
            </div>
            <textarea
              ref={textareaRef}
              className="live-textarea"
              placeholder={activeDomainObj.placeholder}
              value={query}
              onChange={e => setQuery(e.target.value)}
              rows={4}
            />
            <div className="live-query-footer">
              <span className="char-count" style={{ color: query.length > 200 ? 'var(--coral)' : 'var(--text-muted)' }}>
                {query.length} chars
              </span>
            </div>
          </div>

          {/* Example briefs */}
          <div className="examples-section">
            <p className="examples-label">Suggested in {activeDomainObj.name}:</p>
            <div className="examples-list">
              {activeDomainObj.examples.map(brief => (
                <button key={brief} className="example-chip" onClick={() => useExample(brief)}>
                  <ArrowRight size={11} />
                  <span>{brief}</span>
                </button>
              ))}
            </div>
          </div>

          {/* API Mode toggle */}
          <div className="api-mode-section">
            <p className="examples-label">API Mode</p>
            <div className="api-mode-cards">
              <label className={`api-mode-card ${apiMode === 'dry_run' ? 'selected' : ''}`}>
                <input type="radio" name="apiMode" value="dry_run" checked={apiMode === 'dry_run'} onChange={() => { setApiMode('dry_run'); setConfirmed(false); }} />
                <div className="api-mode-icon safe">
                  <ShieldCheck size={18} />
                </div>
                <div className="api-mode-info">
                  <div className="api-mode-title">Safe Dry Run</div>
                  <div className="api-mode-desc">0 quota units · No network calls · Simulates live discovery</div>
                </div>
                {apiMode === 'dry_run' && <div className="api-mode-check"><Check size={14} /></div>}
              </label>

              <label className={`api-mode-card ${apiMode === 'live' ? 'selected live' : ''}`}>
                <input type="radio" name="apiMode" value="live" checked={apiMode === 'live'} onChange={() => setApiMode('live')} />
                <div className="api-mode-icon live">
                  <Zap size={18} />
                </div>
                <div className="api-mode-info">
                  <div className="api-mode-title">Live Network</div>
                  <div className="api-mode-desc">~101 quota units · Real-time YouTube search & stats</div>
                </div>
                {apiMode === 'live' && <div className="api-mode-check live"><Check size={14} /></div>}
              </label>
            </div>

            {apiMode === 'live' && (
              <label className="authorize-check">
                <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.8rem', color: 'var(--gold)' }}>Authorization Required</div>
                  <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: 2 }}>I authorize deduction of ~101 quota units from today's Pacific-time daily ledger (10,000 unit cap).</div>
                </div>
              </label>
            )}
          </div>

          {/* Run button */}
          <button
            className={`live-run-btn ${canRun ? (apiMode === 'live' ? 'live' : 'safe') : 'disabled'}`}
            disabled={!canRun}
            onClick={runSearch}
          >
            {loading ? (
              <><RefreshCw size={18} className="spin" /><span>Discovering creators…</span></>
            ) : apiMode === 'live' ? (
              <><Zap size={18} /><span>Run Live Discovery</span></>
            ) : (
              <><Play size={18} /><span>Run Dry-Run Simulation</span></>
            )}
          </button>

          {/* Quota info */}
          {quotaInfo && (
            <div className="quota-info-row">
              <div className="quota-info-item">
                <span className="quota-info-label">Used Today</span>
                <span className="quota-info-val">{quotaInfo.used_today ?? '—'}</span>
              </div>
              <div className="quota-info-divider" />
              <div className="quota-info-item">
                <span className="quota-info-label">Remaining</span>
                <span className="quota-info-val">{quotaInfo.remaining_units ?? '—'}</span>
              </div>
              <div className="quota-info-divider" />
              <div className="quota-info-item">
                <span className="quota-info-label">Daily Cap</span>
                <span className="quota-info-val">10,000</span>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT — Results Panel */}
        <div className="live-results-panel">
          {!ran && !loading && (
            <div className="live-results-empty">
              <div className="live-results-empty-icon">
                <Radio size={36} color="var(--rose)" strokeWidth={1.5} />
              </div>
              <p className="state-title">Ready to discover creators</p>
              <p className="state-desc">Select a domain or type any query on the left, then run discovery to see real YouTube channels ranked by engagement and fit.</p>
              <div className="live-results-features">
                {[
                  { icon: <Search size={14} />, text: 'Multi-domain: Tech, Gaming, Fitness, Finance, Food, Beauty' },
                  { icon: <Users size={14} />, text: 'Real channel names, subscriber counts & video statistics' },
                  { icon: <ShieldCheck size={14} />, text: 'QuotaGuard protection — dry run first with zero cost' },
                ].map(({ icon, text }) => (
                  <div key={text} className="live-feature-row">
                    <span className="live-feature-icon">{icon}</span>
                    <span>{text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading && (
            <div className="live-results-empty">
              <Activity size={40} className="spin" color="var(--rose)" />
              <p className="state-title" style={{ marginTop: 16 }}>
                {apiMode === 'live' ? 'Querying YouTube API…' : 'Simulating pipeline…'}
              </p>
              <p className="state-desc">Searching and enriching creator channel statistics</p>
            </div>
          )}

          {ran && !loading && (
            <>
              {/* Status banner */}
              {statusMsg && (
                <div className={`live-status-banner ${statusMsg.type}`}>
                  {statusMsg.type === 'success'
                    ? <Check size={16} />
                    : <AlertTriangle size={16} />
                  }
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span>{statusMsg.text}</span>
                    {detectedDomainMeta?.name && (
                      <span style={{ fontSize: '0.72rem', opacity: 0.85 }}>
                        Detected Category: <strong>{detectedDomainMeta.name}</strong>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Dry run info box */}
              {apiMode === 'dry_run' && statusMsg?.type === 'success' && (
                <div className="dry-run-info-box">
                  <ShieldCheck size={20} color="var(--emerald)" />
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--emerald)' }}>Dry Run Completed Successfully</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      No network calls were made. Switch to <strong style={{ color: 'var(--text-secondary)' }}>Live Network</strong> mode and authorize quota deduction to discover real YouTube creators for your brief.
                    </div>
                  </div>
                </div>
              )}

              {/* Results */}
              {results.length > 0 && (
                <div className="live-results-list">
                  <div className="live-results-header">
                    <span className="live-results-title">
                      <Wifi size={15} />
                      Discovered Creators <span className="live-results-count">{results.length}</span>
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>via YouTube Data API v3</span>
                  </div>
                  {results.map((r, idx) => (
                    <LiveCreatorCard
                      key={r.channel_id || idx}
                      creator={r}
                      starred={isStarred(r.channel_id)}
                      onStar={() => onStar({
                        channel_id: r.channel_id,
                        channel_name: r.channel_name,
                        category: r.domain_label || r.topical_focus || 'Creator',
                        size_tier: r.size_tier,
                        promotion_score: r.promotion_potential_score ? `${r.promotion_potential_score}` : '—',
                        subscribers: r.subscribers,
                        typical_reach: '—',
                        promo_lift: '—',
                        channel_url: r.channel_url,
                      })}
                      rank={idx + 1}
                    />
                  ))}
                </div>
              )}

              {results.length === 0 && statusMsg?.type === 'success' && apiMode === 'live' && (
                <div className="state-center" style={{ padding: '40px 0' }}>
                  <div className="state-icon">📭</div>
                  <p className="state-title">No creators discovered</p>
                  <p className="state-desc">Try a different product brief or broader search terms</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Live Creator Card ── */
function LiveCreatorCard({ creator: c, starred, onStar, rank }) {
  const domainColor = {
    technology: 'lavender',
    gaming_entertainment: 'amber',
    fitness_health: 'emerald',
    finance_investing: 'cyan',
    beauty_personal_care: 'rose',
    food_cooking: 'coral',
    travel_adventure: 'gold',
    education_science: 'lavender',
  }[c.domain] || 'rose';

  return (
    <div className="live-creator-card">
      <div className="live-card-rank">#{rank}</div>
      {c.thumbnail_url ? (
        <img
          src={c.thumbnail_url}
          alt={c.channel_name}
          className="live-card-thumb"
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      ) : (
        <div className="creator-avatar" style={{ width: 42, height: 42, fontSize: '1rem', borderRadius: 10, flexShrink: 0 }}>
          {getInitial(c.channel_name)}
        </div>
      )}
      <div className="live-card-info">
        <div className="live-card-name-row">
          <span className="live-card-name">{c.channel_name}</span>
          {c.domain_label && (
            <span className={`live-domain-badge ${domainColor}`}>
              {c.domain_label}
            </span>
          )}
        </div>
        <div className="live-card-meta">
          <span className="live-card-subs">{fmt(c.subscribers)} subs</span>
          <span className="live-card-sep">·</span>
          <span className="live-card-videos">{c.video_count} videos</span>
          {c.size_tier && c.size_tier !== 'Mid' && (
            <>
              <span className="live-card-sep">·</span>
              <span className="tier-badge">{c.size_tier}</span>
            </>
          )}
          {c.topical_focus && (
            <>
              <span className="live-card-sep">·</span>
              <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{c.topical_focus}</span>
            </>
          )}
        </div>
      </div>
      <div className="live-card-actions">
        <button
          className={`bookmark-btn ${starred ? 'active' : ''}`}
          onClick={onStar}
          title={starred ? 'Remove from shortlist' : 'Add to shortlist'}
        >
          <Star size={16} fill={starred ? 'currentColor' : 'none'} />
        </button>
        <a
          href={c.channel_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-card-yt"
          style={{ padding: '6px 12px', fontSize: '0.72rem' }}
        >
          <ExternalLink size={12} />
          <span>View</span>
        </a>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   VAULT CREATOR CARD
══════════════════════════════════════════════════ */
function CreatorCard({ creator: c, starred, onStar, onInspect }) {
  const spark = getSparklinePath(c.sparkline, 320, 50);
  const sparkColors = SPARKLINE_COLOR_MAP[c.trend_badge] || SPARKLINE_COLOR_MAP.STEADY;
  const variant = CARD_VARIANT_MAP[c.trend_badge] || '';
  const badgeColor = BADGE_COLOR_MAP[c.trend_badge_color] || 'slate';
  const score = Math.round(c.promotion_score || 0);

  return (
    <div className={`creator-card ${variant}`} onClick={onInspect}>
      <div className="card-top-bar" />
      <div className="card-header" onClick={e => e.stopPropagation()}>
        <div className={`trend-badge ${badgeColor}`}>
          {BADGE_ICON_MAP[c.trend_badge]}
          <span>{c.trend_badge}</span>
          <span style={{ opacity: 0.7, fontWeight: 600 }}>{c.growth_label}</span>
        </div>
        <button className={`bookmark-btn ${starred ? 'active' : ''}`} onClick={() => onStar(c)} title={starred ? 'Remove' : 'Add to shortlist'}>
          <Star size={17} fill={starred ? 'currentColor' : 'none'} />
        </button>
      </div>

      <div className="card-identity">
        <div className="creator-avatar">{getInitial(c.channel_name)}</div>
        <div>
          <div className="creator-name">{c.channel_name}</div>
          <div className="creator-meta">
            <span className="tier-badge">{c.size_tier}</span>
            <span className="meta-sep">·</span>
            <span className="meta-category">{c.category}</span>
          </div>
        </div>
      </div>

      <div className="sparkline-wrap">
        <svg className="sparkline-svg" viewBox="0 0 320 50" preserveAspectRatio="none">
          <defs>
            <linearGradient id={`sg-${c.channel_id}`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor={sparkColors.fill} stopOpacity="0.3" />
              <stop offset="100%" stopColor={sparkColors.fill} stopOpacity="0" />
            </linearGradient>
          </defs>
          {spark.area && <path d={spark.area} fill={`url(#sg-${c.channel_id})`} />}
          {spark.line && <path d={spark.line} fill="none" stroke={sparkColors.stroke} strokeWidth="2" strokeLinecap="round" />}
        </svg>
      </div>

      <div className="score-section">
        <span className="score-label">Score</span>
        <div className="score-bar-wrap">
          <div className="score-bar-fill" style={{ width: `${score}%` }} />
        </div>
        <span className="score-val">{score}</span>
      </div>

      <div className="card-stats">
        <div className="card-stat">
          <span className="card-stat-label">Subscribers</span>
          <span className="card-stat-val">{fmt(c.subscribers)}</span>
        </div>
        <div className="card-stat">
          <span className="card-stat-label">Typical Reach</span>
          <span className="card-stat-val highlight">{fmt(c.typical_reach)}</span>
        </div>
        <div className="card-stat">
          <span className="card-stat-label">Promo Lift</span>
          <span className="card-stat-val">{c.promo_lift !== 'N/A' ? c.promo_lift : '—'}</span>
        </div>
      </div>

      <div className="card-footer" onClick={e => e.stopPropagation()}>
        <button className="btn-card-inspect" onClick={onInspect}>
          <BarChart2 size={14} /><span>Inspect</span>
        </button>
        <a href={c.channel_url} target="_blank" rel="noopener noreferrer" className="btn-card-yt" title="Open on YouTube">
          <ExternalLink size={13} /><span>YouTube</span>
        </a>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   INSPECT MODAL
══════════════════════════════════════════════════ */
function InspectModal({ creator: c, starred, onStar, onClose }) {
  const score = Math.round(c.promotion_potential_score || 0);
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <div className="creator-avatar" style={{ width: 40, height: 40, fontSize: '0.95rem' }}>{getInitial(c.channel_name)}</div>
            <div>
              <h2>{c.channel_name}</h2>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>{c.category} · {c.size_tier} Tier · {c.channel_id}</p>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="inspect-score-hero">
            <div className="inspect-score-main">
              <div className="inspect-score-eyebrow">Promotion Potential</div>
              <div className="inspect-score-num">{score}<span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 400 }}>/100</span></div>
              <div className="inspect-score-sub">Raw composite: <strong>{(c.raw_score || 0).toFixed(1)}</strong></div>
            </div>
            <div className="inspect-lift-col">
              <div className="inspect-lift-label">Promo Lift</div>
              <div className="inspect-lift-val">{c.promo_lift !== 'N/A' ? c.promo_lift : '—'}</div>
              <div className="inspect-cadence">Cadence: every {(c.upload_cadence_days || 0).toFixed(0)} days</div>
            </div>
          </div>
          <div className="card-stats">
            <div className="card-stat"><span className="card-stat-label">Subscribers</span><span className="card-stat-val">{fmt(c.subscribers)}</span></div>
            <div className="card-stat"><span className="card-stat-label">Total Views</span><span className="card-stat-val">{fmt(c.total_views)}</span></div>
            <div className="card-stat"><span className="card-stat-label">Engagement</span><span className="card-stat-val highlight">{((c.engagement_rate || 0) * 100).toFixed(2)}%</span></div>
            <div className="card-stat"><span className="card-stat-label">Videos</span><span className="card-stat-val">{(c.video_count || 0).toLocaleString()}</span></div>
            <div className="card-stat"><span className="card-stat-label">Typical Reach</span><span className="card-stat-val">{fmt(c.typical_reach)}</span></div>
            <div className="card-stat"><span className="card-stat-label">Sponsored Rate</span><span className="card-stat-val">{(c.sponsored_rate || 0).toFixed(1)}%</span></div>
          </div>
          {c.components && c.components.length > 0 && (
            <div className="components-section">
              <h4>6-Factor Ranking Components</h4>
              <div className="comp-list">
                {c.components.map(comp => (
                  <div key={comp.name} className="comp-row">
                    <div className="comp-row-header">
                      <span className="comp-name">{comp.name}</span>
                      <span className="comp-score-text">{Math.round(comp.score)}% · wt {comp.weight}%</span>
                    </div>
                    <div className="comp-bar-bg">
                      <div className="comp-bar-fill" style={{ width: `${Math.min(100, Math.max(2, comp.score))}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: 10 }}>
            <button className={starred ? 'btn btn-ghost' : 'btn btn-rose'} style={{ flex: 1 }} onClick={() => onStar(c)}>
              <Star size={15} fill={starred ? 'currentColor' : 'none'} />
              <span>{starred ? 'Remove from Shortlist' : 'Add to Shortlist'}</span>
            </button>
            <a href={c.channel_url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost" style={{ textDecoration: 'none' }}>
              <span>YouTube</span><ExternalLink size={14} />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   SHORTLIST MODAL
══════════════════════════════════════════════════ */
function ShortlistModal({ shortlist, onRemove, onExport, onClear, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <Star size={18} color="var(--gold-soft)" fill="var(--gold-soft)" />
            <h2>Campaign Shortlist ({shortlist.length})</h2>
          </div>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          {shortlist.length === 0 ? (
            <div className="state-center" style={{ padding: '40px 0' }}>
              <Star size={36} color="var(--text-muted)" />
              <p className="state-title" style={{ fontSize: '0.95rem' }}>Your shortlist is empty</p>
              <p className="state-desc">Star any creator — from either mode — to save them here</p>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{shortlist.length} creator{shortlist.length !== 1 ? 's' : ''} ready for outreach</p>
                <button className="btn btn-rose" onClick={onExport}><Download size={14} /><span>Export CSV</span></button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {shortlist.map(item => (
                  <div key={item.channel_id} className="shortlist-item">
                    <div className="creator-avatar" style={{ width: 36, height: 36, fontSize: '0.85rem', borderRadius: 8, flexShrink: 0 }}>{getInitial(item.channel_name)}</div>
                    <div className="shortlist-item-info">
                      <div className="shortlist-item-name">{item.channel_name}</div>
                      <div className="shortlist-item-meta">{item.category} · {fmt(item.subscribers)} subs · Score {item.promotion_score}</div>
                    </div>
                    <button className="btn btn-ghost" style={{ padding: '6px 8px', minWidth: 'auto' }} onClick={() => onRemove(item)}><X size={14} /></button>
                  </div>
                ))}
              </div>
              <button className="btn btn-ghost" style={{ color: 'var(--coral)', alignSelf: 'flex-start', marginTop: 4 }} onClick={onClear}>Clear All</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
