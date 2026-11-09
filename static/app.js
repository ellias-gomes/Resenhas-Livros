// ========================================================
// Estado Global do Aplicativo
// ========================================================
const state = {
  token: localStorage.getItem("resenhas_token") || null,
  currentUser: null,
  usersList: [],
  reviews: [],
  skoobPreviewItems: [],
  filters: {
    category: "todos",
    status: "todos",
    userId: null,
    userNameLabel: null,
    favoritesOnly: false,
    search: "",
    sort: "recent",
  },
};

const CATEGORY_META = {
  livro: { icon: "📚", label: "Livro", creatorLabel: "Autor(a) *" },
  filme: { icon: "🎬", label: "Filme", creatorLabel: "Diretor(a) / Estúdio" },
  serie: { icon: "📺", label: "Série", creatorLabel: "Criador(a) / Emissora / Streaming" },
};

const STATUS_META = {
  concluido: { label: "✓ Lido / Assistido", cls: "badge-status-concluido" },
  em_andamento: { label: "📖 Lendo / Assistindo", cls: "badge-status-em_andamento" },
  quero: { label: "✨ Quero ler / assistir", cls: "badge-status-quero" },
  abandonado: { label: "💤 Abandonado", cls: "badge-status-abandonado" },
};

// ========================================================
// Utilitários de API e UI
// ========================================================
async function apiFetch(path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Ocorreu um erro inesperado.");
  }
  return data;
}

function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3600);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderStars(rating) {
  const val = Number(rating) || 0;
  const full = Math.floor(val);
  const half = val - full >= 0.45 ? 1 : 0;
  const empty = Math.max(0, 5 - full - half);
  return "★".repeat(full) + (half ? "½" : "") + "☆".repeat(empty);
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = false;
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function requireAuth(actionCallback) {
  if (!state.currentUser) {
    showToast("Entre na sua conta ou cadastre-se para continuar 💜", "error");
    openModal("authModal");
    return false;
  }
  if (actionCallback) actionCallback();
  return true;
}

// ========================================================
// Inicialização e Carregamento de Dados
// ========================================================
async function initApp() {
  bindEvents();
  renderInteractiveStars(5.0);
  await Promise.all([loadNetworkInfo(), checkSession()]);
  await Promise.all([loadCommunityUsers(), loadReviews()]);

  // Verifica se há âncora #review-123 na URL
  if (window.location.hash.startsWith("#review-")) {
    const targetEl = document.querySelector(window.location.hash);
    if (targetEl) targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

async function loadNetworkInfo() {
  try {
    const info = await apiFetch("/api/network-info");
    const lanText = document.getElementById("lanUrlText");
    if (lanText && info.lan_url) {
      lanText.textContent = info.lan_url;
    }
  } catch (_) {}
}

async function checkSession() {
  if (!state.token) {
    state.currentUser = null;
    renderAuthUI();
    return;
  }
  try {
    const user = await apiFetch("/api/auth/me");
    state.currentUser = user;
  } catch (_) {
    state.token = null;
    state.currentUser = null;
    localStorage.removeItem("resenhas_token");
  }
  renderAuthUI();
}

async function loadCommunityUsers() {
  try {
    state.usersList = await apiFetch("/api/users");
    renderCommunityUsers();
    renderAuthUI();
  } catch (_) {}
}

async function loadReviews() {
  const params = new URLSearchParams();
  if (state.filters.category && state.filters.category !== "todos") {
    params.set("category", state.filters.category);
  }
  if (state.filters.status && state.filters.status !== "todos") {
    params.set("status", state.filters.status);
  }
  if (state.filters.userId) {
    params.set("user_id", state.filters.userId);
  }
  if (state.filters.favoritesOnly) {
    params.set("favorites_only", "true");
  }
  if (state.filters.search.trim()) {
    params.set("search", state.filters.search.trim());
  }
  params.set("sort", state.filters.sort || "recent");

  try {
    state.reviews = await apiFetch(`/api/reviews?${params.toString()}`);
    renderFeed();
    updateFilterBanner();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ========================================================
// Renderização da Interface (Perfil, Topo, Comunidade, Feed)
// ========================================================
function renderAuthUI() {
  const topbarAuth = document.getElementById("topbarAuthArea");
  const sidebarProfile = document.getElementById("sidebarProfileCard");
  const composerAvatar = document.getElementById("composerAvatar");

  if (!state.currentUser) {
    topbarAuth.innerHTML = `
      <button class="btn btn-soft btn-sm" id="topLoginBtn">Entrar</button>
      <button class="btn btn-primary btn-sm" id="topRegisterBtn">Criar Conta</button>
    `;
    document.getElementById("topLoginBtn").onclick = () => {
      switchAuthTab("login");
      openModal("authModal");
    };
    document.getElementById("topRegisterBtn").onclick = () => {
      switchAuthTab("register");
      openModal("authModal");
    };

    sidebarProfile.innerHTML = `
      <div class="avatar-circle" style="background:#e9d5ff">💜</div>
      <div class="profile-name">Bem-vindos(as)!</div>
      <p class="profile-bio">
        Entre ou crie seu perfil para publicar resenhas de livros, filmes e séries, curtir, comentar e importar do Skoob.
      </p>
      <div class="profile-card-actions">
        <button class="btn btn-primary btn-sm" id="sideLoginBtn">Entrar / Cadastrar</button>
      </div>
    `;
    document.getElementById("sideLoginBtn").onclick = () => openModal("authModal");
    if (composerAvatar) {
      composerAvatar.textContent = "🌸";
      composerAvatar.style.background = "#e9d5ff";
    }
    return;
  }

  const u = state.currentUser;
  const userStatsEntry = state.usersList.find((x) => x.user.id === u.id);
  const stats = userStatsEntry
    ? userStatsEntry.stats
    : { livros: 0, filmes: 0, series: 0, favoritos: 0, total_reviews: 0 };

  topbarAuth.innerHTML = `
    <button class="btn btn-soft btn-sm" id="topEditProfileBtn" title="Editar meu perfil">
      ${escapeHtml(u.avatar_emoji || "🌸")} ${escapeHtml(u.display_name)}
    </button>
    <button class="btn btn-ghost btn-sm" id="topLogoutBtn" title="Sair da conta">Sair</button>
  `;
  document.getElementById("topEditProfileBtn").onclick = openProfileEditor;
  document.getElementById("topLogoutBtn").onclick = handleLogout;

  sidebarProfile.innerHTML = `
    <div class="avatar-circle" style="background:${escapeHtml(u.avatar_color || "#d8b4f8")}">
      ${escapeHtml(u.avatar_emoji || "🌸")}
    </div>
    <div class="profile-name">${escapeHtml(u.display_name)}</div>
    <div class="profile-handle">@${escapeHtml(u.username)}</div>
    ${u.bio ? `<p class="profile-bio">${escapeHtml(u.bio)}</p>` : ""}
    <div class="profile-stats-grid">
      <div class="stat-box">
        <span class="stat-num">${stats.livros}</span>
        <span class="stat-label">📚 Livros</span>
      </div>
      <div class="stat-box">
        <span class="stat-num">${stats.filmes}</span>
        <span class="stat-label">🎬 Filmes</span>
      </div>
      <div class="stat-box">
        <span class="stat-num">${stats.series}</span>
        <span class="stat-label">📺 Séries</span>
      </div>
    </div>
    <div class="profile-card-actions">
      <button class="btn btn-soft btn-sm" id="sideEditProfileBtn">✏️ Editar Perfil</button>
      <button class="btn btn-ghost btn-sm" id="sideMyPostsBtn">Minha Estante</button>
    </div>
  `;
  document.getElementById("sideEditProfileBtn").onclick = openProfileEditor;
  document.getElementById("sideMyPostsBtn").onclick = () => {
    filterByUser(u.id, u.display_name);
  };

  if (composerAvatar) {
    composerAvatar.textContent = u.avatar_emoji || "🌸";
    composerAvatar.style.background = u.avatar_color || "#d8b4f8";
  }
}

function renderCommunityUsers() {
  const container = document.getElementById("communityUsersList");
  const clearBtn = document.getElementById("clearUserFilterBtn");
  clearBtn.style.display = state.filters.userId ? "inline-block" : "none";

  if (!state.usersList.length) {
    container.innerHTML = `<p class="card-helper">Nenhum perfil cadastrado ainda.</p>`;
    return;
  }

  container.innerHTML = state.usersList
    .map(({ user, stats }) => {
      const isActive = state.filters.userId === user.id;
      return `
        <div class="community-user-row ${isActive ? "active" : ""}" data-uid="${user.id}" data-uname="${escapeHtml(user.display_name)}">
          <div class="avatar-circle avatar-sm" style="background:${escapeHtml(user.avatar_color || "#d8b4f8")}">
            ${escapeHtml(user.avatar_emoji || "🌸")}
          </div>
          <div class="community-user-meta">
            <div class="community-user-name">${escapeHtml(user.display_name)} <span class="author-username">@${escapeHtml(user.username)}</span></div>
            <div class="community-user-counts">
              📚 ${stats.livros} · 🎬 ${stats.filmes} · 📺 ${stats.series}
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".community-user-row").forEach((row) => {
    row.onclick = () => {
      const uid = Number(row.dataset.uid);
      const uname = row.dataset.uname;
      if (state.filters.userId === uid) {
        filterByUser(null, null);
      } else {
        filterByUser(uid, uname);
      }
    };
  });
}

function updateFilterBanner() {
  const banner = document.getElementById("activeFilterBanner");
  const parts = [];
  if (state.filters.userNameLabel) {
    parts.push(`Estante de ${state.filters.userNameLabel}`);
  }
  if (state.filters.favoritesOnly) {
    parts.push("💖 Apenas Favoritos");
  }
  if (state.filters.category !== "todos") {
    const meta = CATEGORY_META[state.filters.category];
    if (meta) parts.push(`${meta.icon} ${meta.label}s`);
  }
  if (state.filters.search.trim()) {
    parts.push(`Busca: "${state.filters.search.trim()}"`);
  }
  banner.textContent = parts.length
    ? `${parts.join(" · ")} (${state.reviews.length})`
    : `Exibindo todas as publicações (${state.reviews.length})`;
}

function renderFeed() {
  const container = document.getElementById("reviewsFeedContainer");
  if (!state.reviews.length) {
    container.innerHTML = `
      <div class="empty-feed-box">
        <div class="empty-feed-icon">🌷</div>
        <h3>Nenhuma resenha encontrada por aqui ainda!</h3>
        <p style="color:var(--text-secondary); margin: 0.45rem 0 1.1rem;">
          Que tal publicar sua primeira avaliação de livro, filme ou série, ou importar sua estante do Skoob?
        </p>
        <div style="display:flex; gap:0.6rem; justify-content:center; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="openNewReviewModal()">✨ Escrever Resenha</button>
          <button class="btn btn-skoob" onclick="openSkoobImportModal()">🦉 Importar do Skoob</button>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = state.reviews.map(renderReviewCardHtml).join("");
  bindFeedCardEvents(container);
}

function renderReviewCardHtml(rev) {
  const isRepost = Boolean(rev.original_review_id);
  const displaySource = rev.original_review || rev;
  const catMeta = CATEGORY_META[rev.category] || CATEGORY_META.livro;
  const statusMeta = STATUS_META[rev.status] || STATUS_META.concluido;
  const isOwner = state.currentUser && state.currentUser.id === rev.user_id;

  const coverHtml = rev.cover_url
    ? `<img src="${escapeHtml(rev.cover_url)}" alt="${escapeHtml(rev.work_title)}" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
       <div class="work-cover-placeholder" style="display:none;"><span class="icon">${catMeta.icon}</span><span>${escapeHtml(rev.work_title.slice(0, 28))}</span></div>`
    : `<div class="work-cover-placeholder"><span class="icon">${catMeta.icon}</span><span>${escapeHtml(rev.work_title.slice(0, 28))}</span></div>`;

  const repostHeaderHtml = isRepost
    ? `
      <div class="repost-banner">
        🔁 <strong>${escapeHtml(rev.author.display_name)}</strong> (@${escapeHtml(rev.author.username)}) republicou no feed
        ${rev.original_review ? ` a resenha de <strong>${escapeHtml(rev.original_review.author.display_name)}</strong>` : ""}
      </div>
      ${rev.repost_comment ? `<div class="repost-quote-box">“${escapeHtml(rev.repost_comment)}”</div>` : ""}
    `
    : "";

  const cardAuthor = isRepost && rev.original_review ? rev.original_review.author : rev.author;

  const commentsHtml = (rev.comments || [])
    .map((c) => {
      const canDeleteComment =
        state.currentUser && (state.currentUser.id === c.user_id || state.currentUser.id === rev.user_id);
      return `
        <div class="comment-item">
          <div class="avatar-circle comment-avatar" style="background:${escapeHtml(c.author.avatar_color || "#d8b4f8")}">
            ${escapeHtml(c.author.avatar_emoji || "🌸")}
          </div>
          <div class="comment-body">
            <div>
              <span class="comment-author">${escapeHtml(c.author.display_name)}</span>
              <span class="comment-time">${formatDate(c.created_at)}</span>
            </div>
            <div class="comment-text">${escapeHtml(c.content)}</div>
          </div>
          ${
            canDeleteComment
              ? `<button class="comment-delete-btn" data-del-comment="${c.id}" title="Excluir comentário">🗑️</button>`
              : ""
          }
        </div>
      `;
    })
    .join("");

  return `
    <article class="review-card" id="review-${rev.id}" data-review-id="${rev.id}">
      ${repostHeaderHtml}

      <div class="review-header">
        <div class="review-author-info" data-filter-user="${cardAuthor.id}" data-filter-uname="${escapeHtml(cardAuthor.display_name)}">
          <div class="avatar-circle avatar-sm" style="background:${escapeHtml(cardAuthor.avatar_color || "#d8b4f8")}">
            ${escapeHtml(cardAuthor.avatar_emoji || "🌸")}
          </div>
          <div>
            <div class="author-name-line">
              <span class="author-display-name">${escapeHtml(cardAuthor.display_name)}</span>
              <span class="author-username">@${escapeHtml(cardAuthor.username)}</span>
            </div>
            <div class="review-date">${formatDate(displaySource.created_at)}</div>
          </div>
        </div>

        <div class="review-badges">
          <span class="badge badge-${escapeHtml(rev.category)}">${catMeta.icon} ${catMeta.label}</span>
          <span class="badge ${statusMeta.cls}">${statusMeta.label}</span>
          ${rev.is_favorite ? `<span class="badge badge-fav">💖 Favorito</span>` : ""}
          ${
            rev.skoob_url
              ? `<a href="${escapeHtml(rev.skoob_url)}" target="_blank" rel="noopener" class="badge badge-skoob">🦉 Skoob ↗</a>`
              : rev.skoob_book_id
              ? `<span class="badge badge-skoob">🦉 Skoob</span>`
              : ""
          }
        </div>
      </div>

      <!-- Showcase da Obra -->
      <div class="work-showcase">
        <div class="work-cover-wrap">
          ${coverHtml}
        </div>
        <div class="work-details">
          <h3 class="work-title">${escapeHtml(rev.work_title)}</h3>
          ${rev.work_creator ? `<div class="work-creator">${escapeHtml(rev.work_creator)}</div>` : ""}
          <div class="work-meta-tags">
            ${rev.work_genre ? `<span>🏷️ ${escapeHtml(rev.work_genre)}</span>` : ""}
            ${rev.work_year ? `<span>📅 ${escapeHtml(rev.work_year)}</span>` : ""}
            ${rev.finished_at ? `<span>✨ Concluído em: ${escapeHtml(rev.finished_at)}</span>` : ""}
          </div>
          <div class="work-rating-row">
            <span class="stars-display">${renderStars(rev.rating)}</span>
            <span class="rating-number-pill">${Number(rev.rating).toFixed(1)} / 5.0</span>
          </div>
        </div>
      </div>

      <!-- Texto da Resenha -->
      ${rev.title ? `<h4 class="review-headline">${escapeHtml(rev.title)}</h4>` : ""}
      <div class="spoiler-box ${rev.has_spoiler ? "blurred" : ""}">
        <div class="review-body-text">${escapeHtml(rev.content)}</div>
        ${
          rev.has_spoiler
            ? `<div class="spoiler-overlay-btn" data-reveal-spoiler>
                 <span>⚠️ Contém Spoiler — Clique para ler a resenha</span>
               </div>`
            : ""
        }
      </div>

      <!-- Barra de Ações Sociais -->
      <div class="review-actions-bar">
        <div class="social-btns-left">
          <button class="action-btn ${rev.liked_by_me ? "liked" : ""}" data-like-review="${rev.id}">
            <span>${rev.liked_by_me ? "💜" : "🤍"}</span>
            <span>Curtir (${rev.likes_count})</span>
          </button>
          <button class="action-btn" data-toggle-comments="${rev.id}">
            <span>💬</span>
            <span>Comentários (${rev.comments_count})</span>
          </button>
          <button class="action-btn" data-repost-review="${rev.id}">
            <span>🔁</span>
            <span>Republicar / Compartilhar (${rev.reposts_count})</span>
          </button>
        </div>

        ${
          isOwner
            ? `
          <div class="owner-btns-right">
            <button class="action-btn" data-edit-review="${rev.id}" title="Editar resenha">✏️ Editar</button>
            <button class="action-btn delete-btn" data-delete-review="${rev.id}" title="Apagar resenha">🗑️ Apagar</button>
          </div>
        `
            : ""
        }
      </div>

      <!-- Área de Comentários -->
      <div class="comments-section" id="comments-box-${rev.id}" ${rev.comments_count > 0 ? "" : "hidden"}>
        <div class="comments-list">
          ${commentsHtml}
        </div>
        <form class="comment-form" data-comment-form="${rev.id}">
          <input type="text" placeholder="Escreva um comentário carinhoso..." required maxlength="1000" />
          <button type="submit" class="btn btn-primary btn-sm">Enviar</button>
        </form>
      </div>
    </article>
  `;
}

function bindFeedCardEvents(container) {
  // Revelar spoiler
  container.querySelectorAll("[data-reveal-spoiler]").forEach((btn) => {
    btn.onclick = () => {
      const box = btn.closest(".spoiler-box");
      if (box) box.classList.remove("blurred");
      btn.remove();
    };
  });

  // Filtrar por autor ao clicar no cabeçalho
  container.querySelectorAll("[data-filter-user]").forEach((el) => {
    el.onclick = () => {
      filterByUser(Number(el.dataset.filterUser), el.dataset.filterUname);
    };
  });

  // Curtir
  container.querySelectorAll("[data-like-review]").forEach((btn) => {
    btn.onclick = async () => {
      if (!requireAuth()) return;
      const id = Number(btn.dataset.likeReview);
      try {
        await apiFetch(`/api/reviews/${id}/like`, { method: "POST" });
        await loadReviews();
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  });

  // Abrir/fechar caixa de comentários
  container.querySelectorAll("[data-toggle-comments]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.dataset.toggleComments;
      const box = document.getElementById(`comments-box-${id}`);
      if (box) {
        box.hidden = !box.hidden;
        if (!box.hidden) {
          const inp = box.querySelector("input");
          if (inp) inp.focus();
        }
      }
    };
  });

  // Enviar comentário
  container.querySelectorAll("[data-comment-form]").forEach((form) => {
    form.onsubmit = async (e) => {
      e.preventDefault();
      if (!requireAuth()) return;
      const id = Number(form.dataset.commentForm);
      const input = form.querySelector("input");
      const content = input.value.trim();
      if (!content) return;
      try {
        await apiFetch(`/api/reviews/${id}/comments`, {
          method: "POST",
          body: JSON.stringify({ content }),
        });
        input.value = "";
        await loadReviews();
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  });

  // Excluir comentário
  container.querySelectorAll("[data-del-comment]").forEach((btn) => {
    btn.onclick = async () => {
      const cid = Number(btn.dataset.delComment);
      try {
        await apiFetch(`/api/comments/${cid}`, { method: "DELETE" });
        await loadReviews();
        showToast("Comentário removido.");
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  });

  // Republicar / Compartilhar
  container.querySelectorAll("[data-repost-review]").forEach((btn) => {
    btn.onclick = () => {
      const id = Number(btn.dataset.repostReview);
      const rev = state.reviews.find((r) => r.id === id);
      if (!rev) return;
      document.getElementById("repostTargetReviewId").value = rev.id;
      document.getElementById("repostTargetSummary").innerHTML = `
        Obra: <strong>${escapeHtml(rev.work_title)}</strong> — Resenha por <strong>${escapeHtml(rev.author.display_name)}</strong>
      `;
      document.getElementById("repostCommentInput").value = "";
      openModal("repostModal");
    };
  });

  // Editar resenha
  container.querySelectorAll("[data-edit-review]").forEach((btn) => {
    btn.onclick = () => {
      const id = Number(btn.dataset.editReview);
      const rev = state.reviews.find((r) => r.id === id);
      if (rev) openEditReviewModal(rev);
    };
  });

  // Excluir resenha
  container.querySelectorAll("[data-delete-review]").forEach((btn) => {
    btn.onclick = async () => {
      const id = Number(btn.dataset.deleteReview);
      if (!confirm("Tem certeza que deseja apagar esta resenha?")) return;
      try {
        await apiFetch(`/api/reviews/${id}`, { method: "DELETE" });
        showToast("Resenha apagada com sucesso.");
        await Promise.all([loadReviews(), loadCommunityUsers()]);
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  });
}

// ========================================================
// Criação e Edição de Resenha + Estrelas + Busca Automática
// ========================================================
function renderInteractiveStars(selectedRating) {
  const container = document.getElementById("interactiveStars");
  const display = document.getElementById("ratingValueDisplay");
  const slider = document.getElementById("ratingRangeInput");
  const val = Number(selectedRating) || 5.0;

  if (display) display.textContent = `${val.toFixed(1)} ★`;
  if (slider) slider.value = val;

  if (!container) return;
  container.innerHTML = [1, 2, 3, 4, 5]
    .map((starNum) => {
      const isActive = val >= starNum - 0.25;
      return `<span class="star-btn ${isActive ? "active" : ""}" data-star-val="${starNum}">★</span>`;
    })
    .join("");

  container.querySelectorAll(".star-btn").forEach((el) => {
    el.onclick = () => {
      const starVal = Number(el.dataset.starVal);
      renderInteractiveStars(starVal);
    };
  });
}

function setFormCategory(cat) {
  const validCat = CATEGORY_META[cat] ? cat : "livro";
  document.getElementById("reviewCategoryInput").value = validCat;
  document.getElementById("workCreatorLabel").textContent = CATEGORY_META[validCat].creatorLabel;
  document.querySelectorAll("#formCategoryTabs .cat-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.cat === validCat);
  });
}

function openNewReviewModal(defaultCategory = "livro") {
  if (!requireAuth()) return;
  document.getElementById("reviewModalTitle").textContent = "✨ Nova Resenha";
  document.getElementById("saveReviewSubmitBtn").textContent = "Publicar Resenha 💜";
  document.getElementById("reviewIdInput").value = "";
  document.getElementById("reviewForm").reset();
  document.getElementById("catalogSearchResults").hidden = true;
  setFormCategory(defaultCategory);
  renderInteractiveStars(5.0);
  openModal("reviewModal");
}

function openEditReviewModal(rev) {
  if (!requireAuth()) return;
  document.getElementById("reviewModalTitle").textContent = "✏️ Editar Resenha";
  document.getElementById("saveReviewSubmitBtn").textContent = "Salvar Alterações 💜";
  document.getElementById("reviewIdInput").value = rev.id;
  setFormCategory(rev.category || "livro");
  document.getElementById("workTitleInput").value = rev.work_title || "";
  document.getElementById("workCreatorInput").value = rev.work_creator || "";
  document.getElementById("workGenreInput").value = rev.work_genre || "";
  document.getElementById("workYearInput").value = rev.work_year || "";
  document.getElementById("finishedAtInput").value = rev.finished_at || "";
  document.getElementById("reviewStatusInput").value = rev.status || "concluido";
  document.getElementById("coverUrlInput").value = rev.cover_url || "";
  document.getElementById("reviewTitleInput").value = rev.title || "";
  document.getElementById("reviewContentInput").value = rev.content || "";
  document.getElementById("isFavoriteInput").checked = Boolean(rev.is_favorite);
  document.getElementById("hasSpoilerInput").checked = Boolean(rev.has_spoiler);
  document.getElementById("catalogSearchResults").hidden = true;
  renderInteractiveStars(rev.rating || 5.0);
  openModal("reviewModal");
}

async function handleCatalogSearch() {
  const q = document.getElementById("catalogSearchInput").value.trim();
  const category = document.getElementById("reviewCategoryInput").value || "livro";
  const resultsBox = document.getElementById("catalogSearchResults");
  if (q.length < 2) {
    showToast("Digite pelo menos 2 letras para buscar a obra.", "error");
    return;
  }

  const btn = document.getElementById("btnCatalogSearch");
  btn.disabled = true;
  btn.textContent = "Buscando...";

  try {
    const data = await apiFetch(
      `/api/media/search?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`
    );
    const items = data.items || [];
    resultsBox.hidden = false;
    if (!items.length) {
      resultsBox.innerHTML = `<p style="font-size:0.8rem; color:var(--text-muted);">Nenhum resultado automático encontrado. Você pode preencher manualmente abaixo!</p>`;
      return;
    }

    resultsBox.innerHTML = items
      .map(
        (it, idx) => `
        <div class="catalog-item-card" data-cat-idx="${idx}">
          ${it.cover_url ? `<img src="${escapeHtml(it.cover_url)}" alt="" />` : `<div style="width:38px;height:54px;background:var(--purple-100);border-radius:4px;display:flex;align-items:center;justify-content:center;">📚</div>`}
          <div class="catalog-item-info">
            <strong>${escapeHtml(it.work_title)}</strong>
            <div>${escapeHtml(it.work_creator || "")} ${it.work_year ? `(${escapeHtml(it.work_year)})` : ""}</div>
          </div>
        </div>
      `
      )
      .join("");

    resultsBox.querySelectorAll(".catalog-item-card").forEach((card) => {
      card.onclick = () => {
        const picked = items[Number(card.dataset.catIdx)];
        if (!picked) return;
        document.getElementById("workTitleInput").value = picked.work_title || "";
        document.getElementById("workCreatorInput").value = picked.work_creator || "";
        document.getElementById("workGenreInput").value = picked.work_genre || "";
        document.getElementById("workYearInput").value = picked.work_year || "";
        document.getElementById("coverUrlInput").value = picked.cover_url || "";
        resultsBox.hidden = true;
        showToast("Dados e capa preenchidos automaticamente! ✨");
      };
    });
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Buscar Obra";
  }
}

// ========================================================
// Fluxo de Importação do Skoob
// ========================================================
function openSkoobImportModal() {
  if (!requireAuth()) return;
  state.skoobPreviewItems = [];
  document.getElementById("skoobPreviewSection").hidden = true;
  if (state.currentUser && state.currentUser.skoob_id && !document.getElementById("skoobUrlOrIdInput").value) {
    document.getElementById("skoobUrlOrIdInput").value = state.currentUser.skoob_id;
  }
  openModal("skoobModal");
}

function renderSkoobPreview(items) {
  state.skoobPreviewItems = items.map((it) => ({ ...it, _selected: true }));
  const section = document.getElementById("skoobPreviewSection");
  const title = document.getElementById("skoobPreviewCountTitle");
  const list = document.getElementById("skoobPreviewList");

  section.hidden = false;
  title.textContent = `${items.length} avaliação(ões) encontrada(s) no Skoob`;

  list.innerHTML = state.skoobPreviewItems
    .map(
      (item, idx) => `
      <div class="skoob-preview-item">
        <input type="checkbox" class="skoob-item-check" data-idx="${idx}" checked />
        ${
          item.cover_url
            ? `<img src="${escapeHtml(item.cover_url)}" alt="" />`
            : `<div style="width:36px;height:52px;background:var(--purple-200);border-radius:4px;display:flex;align-items:center;justify-content:center;">📚</div>`
        }
        <div class="skoob-preview-meta">
          <strong>${escapeHtml(item.work_title)}</strong>
          <div>${escapeHtml(item.work_creator || "Autor não informado")} · <span style="color:#d97706;font-weight:700;">${Number(item.rating || 5).toFixed(1)} ★</span></div>
          <div style="color:var(--text-muted); font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            ${escapeHtml((item.content || "").slice(0, 110))}
          </div>
        </div>
        <button type="button" class="btn btn-sm btn-soft" data-edit-before-import="${idx}" title="Abrir no editor para revisar antes de publicar">
          ✏️ Editar e Publicar
        </button>
      </div>
    `
    )
    .join("");

  list.querySelectorAll(".skoob-item-check").forEach((chk) => {
    chk.onchange = () => {
      const idx = Number(chk.dataset.idx);
      if (state.skoobPreviewItems[idx]) {
        state.skoobPreviewItems[idx]._selected = chk.checked;
      }
    };
  });

  list.querySelectorAll("[data-edit-before-import]").forEach((btn) => {
    btn.onclick = () => {
      const idx = Number(btn.dataset.editBeforeImport);
      const item = state.skoobPreviewItems[idx];
      if (!item) return;
      closeModal("skoobModal");
      openNewReviewModal(item.category || "livro");
      document.getElementById("workTitleInput").value = item.work_title || "";
      document.getElementById("workCreatorInput").value = item.work_creator || "";
      document.getElementById("workGenreInput").value = item.work_genre || "";
      document.getElementById("workYearInput").value = item.work_year || "";
      document.getElementById("finishedAtInput").value = item.finished_at || "";
      document.getElementById("reviewStatusInput").value = item.status || "concluido";
      document.getElementById("coverUrlInput").value = item.cover_url || "";
      document.getElementById("reviewTitleInput").value = item.title || "";
      document.getElementById("reviewContentInput").value = item.content || "";
      document.getElementById("isFavoriteInput").checked = Boolean(item.is_favorite);
      document.getElementById("hasSpoilerInput").checked = Boolean(item.has_spoiler);
      renderInteractiveStars(item.rating || 5.0);
    };
  });
}

// ========================================================
// Filtros de Navegação
// ========================================================
function filterByUser(userId, displayName) {
  state.filters.userId = userId;
  state.filters.userNameLabel = displayName;
  renderCommunityUsers();
  loadReviews();
}

function switchAuthTab(tab) {
  document.querySelectorAll(".auth-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.authTab === tab);
  });
  document.getElementById("loginForm").hidden = tab !== "login";
  document.getElementById("registerForm").hidden = tab !== "register";
  document.getElementById("authModalTitle").textContent =
    tab === "login" ? "💜 Entrar no Entrelinhas & Telas" : "✨ Criar Conta na Rede";
}

function openProfileEditor() {
  if (!state.currentUser) return;
  const u = state.currentUser;
  document.getElementById("profDisplayName").value = u.display_name || "";
  document.getElementById("profBio").value = u.bio || "";
  document.getElementById("profEmoji").value = u.avatar_emoji || "🌸";
  document.getElementById("profColor").value = u.avatar_color || "#d8b4f8";
  document.getElementById("profSkoobId").value = u.skoob_id || "";
  openModal("profileModal");
}

async function handleLogout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (_) {}
  state.token = null;
  state.currentUser = null;
  localStorage.removeItem("resenhas_token");
  renderAuthUI();
  loadReviews();
  showToast("Você saiu da sua conta. Até logo! 💜");
}

// ========================================================
// Eventos Globais da Página
// ========================================================
function bindEvents() {
  // Fechar modais
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.onclick = () => closeModal(btn.dataset.closeModal);
  });
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.hidden = true;
    });
  });

  // Voltar ao início ao clicar na logo
  document.getElementById("brandHomeBtn").onclick = () => {
    state.filters = {
      category: "todos",
      status: "todos",
      userId: null,
      userNameLabel: null,
      favoritesOnly: false,
      search: "",
      sort: "recent",
    };
    document.getElementById("searchInput").value = "";
    document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
    document.querySelector('.nav-item[data-category="todos"]').classList.add("active");
    document.querySelectorAll(".status-pill").forEach((p) => p.classList.remove("active"));
    document.querySelector('.status-pill[data-status="todos"]').classList.add("active");
    renderCommunityUsers();
    loadReviews();
  };

  // Botões de Nova Resenha e Skoob
  document.getElementById("btnOpenNewReview").onclick = () => openNewReviewModal("livro");
  document.getElementById("quickComposerTrigger").onclick = () => openNewReviewModal("livro");
  document.querySelectorAll("[data-quick-cat]").forEach((btn) => {
    btn.onclick = () => openNewReviewModal(btn.dataset.quickCat);
  });
  document.getElementById("btnOpenSkoobModal").onclick = openSkoobImportModal;
  document.getElementById("quickSkoobBtn").onclick = openSkoobImportModal;

  // Menu lateral de categorias e coleções
  document.querySelectorAll(".nav-item[data-category]").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.filters.category = btn.dataset.category;
      state.filters.favoritesOnly = false;
      state.filters.userId = null;
      state.filters.userNameLabel = null;
      renderCommunityUsers();
      loadReviews();
    };
  });

  document.getElementById("navMyShelfBtn").onclick = () => {
    if (!requireAuth()) return;
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.getElementById("navMyShelfBtn").classList.add("active");
    state.filters.favoritesOnly = false;
    filterByUser(state.currentUser.id, state.currentUser.display_name);
  };

  document.getElementById("navFavoritesBtn").onclick = () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.getElementById("navFavoritesBtn").classList.add("active");
    state.filters.favoritesOnly = true;
    loadReviews();
  };

  // Pílulas de status (Lido/Assistido, Lendo, Quero, Abandonado)
  document.querySelectorAll("#statusFilterPills .status-pill").forEach((pill) => {
    pill.onclick = () => {
      document.querySelectorAll("#statusFilterPills .status-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.filters.status = pill.dataset.status;
      loadReviews();
    };
  });

  // Ordenação e Busca
  document.getElementById("sortSelect").onchange = (e) => {
    state.filters.sort = e.target.value;
    loadReviews();
  };

  let searchTimeout = null;
  document.getElementById("searchInput").oninput = (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.filters.search = e.target.value;
      loadReviews();
    }, 280);
  };

  document.getElementById("clearUserFilterBtn").onclick = () => filterByUser(null, null);

  // Copiar link da rede doméstica
  document.getElementById("copyLanUrlBtn").onclick = () => {
    const text = document.getElementById("lanUrlText").textContent;
    navigator.clipboard.writeText(text).then(() => {
      showToast("Endereço da rede copiado! Envie para acessar de outro dispositivo 💜");
    });
  };

  // Seletor de categoria dentro do modal de resenha
  document.querySelectorAll("#formCategoryTabs .cat-tab").forEach((btn) => {
    btn.onclick = () => setFormCategory(btn.dataset.cat);
  });

  // Slider de nota (meia em meia estrela)
  document.getElementById("ratingRangeInput").oninput = (e) => {
    renderInteractiveStars(Number(e.target.value));
  };

  // Busca automática de catálogo (capa/autor)
  document.getElementById("btnCatalogSearch").onclick = handleCatalogSearch;
  document.getElementById("catalogSearchInput").onkeydown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleCatalogSearch();
    }
  };

  // Upload de foto de capa do computador/celular (Data URL)
  document.getElementById("coverFileInput").onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      document.getElementById("coverUrlInput").value = reader.result;
      showToast("Imagem carregada com sucesso! 📷");
    };
    reader.readAsDataURL(file);
  };

  // Submissão do formulário de Criar / Editar Resenha
  document.getElementById("reviewForm").onsubmit = async (e) => {
    e.preventDefault();
    if (!requireAuth()) return;

    const reviewId = document.getElementById("reviewIdInput").value;
    const payload = {
      category: document.getElementById("reviewCategoryInput").value || "livro",
      work_title: document.getElementById("workTitleInput").value.trim(),
      work_creator: document.getElementById("workCreatorInput").value.trim(),
      work_genre: document.getElementById("workGenreInput").value.trim(),
      work_year: document.getElementById("workYearInput").value.trim(),
      finished_at: document.getElementById("finishedAtInput").value.trim(),
      status: document.getElementById("reviewStatusInput").value,
      rating: Number(document.getElementById("ratingRangeInput").value) || 5.0,
      cover_url: document.getElementById("coverUrlInput").value.trim(),
      title: document.getElementById("reviewTitleInput").value.trim(),
      content: document.getElementById("reviewContentInput").value.trim(),
      is_favorite: document.getElementById("isFavoriteInput").checked,
      has_spoiler: document.getElementById("hasSpoilerInput").checked,
    };

    try {
      if (reviewId) {
        await apiFetch(`/api/reviews/${reviewId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        showToast("Resenha atualizada com sucesso! ✨");
      } else {
        await apiFetch("/api/reviews", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        showToast("Resenha publicada no feed! 💜");
      }
      closeModal("reviewModal");
      await Promise.all([loadReviews(), loadCommunityUsers()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // Abas do Modal de Login / Cadastro
  document.querySelectorAll(".auth-tab").forEach((btn) => {
    btn.onclick = () => switchAuthTab(btn.dataset.authTab);
  });

  // Pickers de emoji e cor no cadastro
  document.querySelectorAll("#regEmojiPicker .emoji-choice").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#regEmojiPicker .emoji-choice").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      document.getElementById("regEmojiInput").value = btn.dataset.emoji;
    };
  });
  document.querySelectorAll("#regColorPicker .color-choice").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#regColorPicker .color-choice").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      document.getElementById("regColorInput").value = btn.dataset.color;
    };
  });

  // Login Submit
  document.getElementById("loginForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const data = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          login: document.getElementById("loginIdentifier").value.trim(),
          password: document.getElementById("loginPassword").value,
        }),
      });
      state.token = data.token;
      state.currentUser = data.user;
      localStorage.setItem("resenhas_token", data.token);
      closeModal("authModal");
      renderAuthUI();
      await Promise.all([loadReviews(), loadCommunityUsers()]);
      showToast(`Que bom te ver, ${data.user.display_name}! 💜`);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // Cadastro Submit
  document.getElementById("registerForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const data = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          display_name: document.getElementById("regDisplayName").value.trim(),
          username: document.getElementById("regUsername").value.trim(),
          email: document.getElementById("regEmail").value.trim(),
          password: document.getElementById("regPassword").value,
          avatar_emoji: document.getElementById("regEmojiInput").value,
          avatar_color: document.getElementById("regColorInput").value,
          bio: document.getElementById("regBio").value.trim(),
        }),
      });
      state.token = data.token;
      state.currentUser = data.user;
      localStorage.setItem("resenhas_token", data.token);
      closeModal("authModal");
      renderAuthUI();
      await Promise.all([loadReviews(), loadCommunityUsers()]);
      showToast(`Conta criada com sucesso! Bem-vinda(o), ${data.user.display_name}! 🌸`);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // Editar Perfil Submit
  document.getElementById("profileForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const updated = await apiFetch("/api/users/me", {
        method: "PUT",
        body: JSON.stringify({
          display_name: document.getElementById("profDisplayName").value.trim(),
          bio: document.getElementById("profBio").value.trim(),
          avatar_emoji: document.getElementById("profEmoji").value.trim() || "🌸",
          avatar_color: document.getElementById("profColor").value,
          skoob_id: document.getElementById("profSkoobId").value.trim(),
        }),
      });
      state.currentUser = updated;
      closeModal("profileModal");
      await Promise.all([loadCommunityUsers(), loadReviews()]);
      showToast("Perfil atualizado com sucesso! 🌷");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // Republicar e Compartilhar
  document.getElementById("repostForm").onsubmit = async (e) => {
    e.preventDefault();
    if (!requireAuth()) return;
    const revId = document.getElementById("repostTargetReviewId").value;
    const comment = document.getElementById("repostCommentInput").value.trim();
    try {
      await apiFetch(`/api/reviews/${revId}/repost`, {
        method: "POST",
        body: JSON.stringify({ repost_comment: comment }),
      });
      closeModal("repostModal");
      await loadReviews();
      showToast("Resenha republicada no feed! 🔁💜");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  document.getElementById("btnCopyShareLink").onclick = () => {
    const revId = document.getElementById("repostTargetReviewId").value;
    const lanBase = document.getElementById("lanUrlText").textContent || window.location.origin;
    const shareUrl = `${lanBase}/#review-${revId}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      showToast("Link direto da resenha copiado! 🔗");
    });
  };

  // Abas do Modal Skoob
  document.querySelectorAll(".skoob-tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".skoob-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const mode = tab.dataset.skoobTab;
      document.getElementById("skoobTabUrl").hidden = mode !== "url";
      document.getElementById("skoobTabFile").hidden = mode !== "file";
    };
  });

  // Buscar Skoob por URL ou ID
  document.getElementById("btnFetchSkoobUrl").onclick = async () => {
    const urlOrId = document.getElementById("skoobUrlOrIdInput").value.trim();
    if (!urlOrId) {
      showToast("Informe o link da resenha, link do perfil ou ID do Skoob.", "error");
      return;
    }
    const btn = document.getElementById("btnFetchSkoobUrl");
    btn.disabled = true;
    btn.textContent = "Buscando...";
    try {
      const res = await apiFetch("/api/skoob/preview-url", {
        method: "POST",
        body: JSON.stringify({ url_or_id: urlOrId, max_items: 150 }),
      });
      renderSkoobPreview(res.items || []);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Buscar no Skoob";
    }
  };

  // Upload de arquivo Skoob (CSV, JSON, HTML)
  document.getElementById("skoobFileInput").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await apiFetch("/api/skoob/preview-file", {
        method: "POST",
        body: formData,
      });
      renderSkoobPreview(res.items || []);
      showToast(`${res.count} avaliação(ões) lida(s) do arquivo!`);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // Selecionar / Desmarcar todos no preview do Skoob
  document.getElementById("btnSelectAllSkoob").onclick = () => {
    const allSelected = state.skoobPreviewItems.every((i) => i._selected);
    state.skoobPreviewItems.forEach((i) => (i._selected = !allSelected));
    document.querySelectorAll(".skoob-item-check").forEach((chk) => {
      chk.checked = !allSelected;
    });
  };

  // Confirmar importação em lote do Skoob
  document.getElementById("btnConfirmSkoobImport").onclick = async () => {
    const selected = state.skoobPreviewItems.filter((i) => i._selected);
    if (!selected.length) {
      showToast("Selecione pelo menos um item para importar.", "error");
      return;
    }
    const skipDuplicates = document.getElementById("skoobSkipDuplicatesCheck").checked;
    const btn = document.getElementById("btnConfirmSkoobImport");
    btn.disabled = true;
    btn.textContent = "Importando...";
    try {
      const res = await apiFetch(`/api/skoob/import-batch?skip_duplicates=${skipDuplicates}`, {
        method: "POST",
        body: JSON.stringify(selected),
      });
      showToast(res.message || "Importação concluída!");
      closeModal("skoobModal");
      await Promise.all([loadReviews(), loadCommunityUsers()]);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Importar Selecionados 💜";
    }
  };
}

document.addEventListener("DOMContentLoaded", initApp);
