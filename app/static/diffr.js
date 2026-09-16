function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'light' ? '' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('diffr-theme', next || 'dark');
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
        hljsLink.href = next === 'light'
            ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css'
            : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark-dimmed.min.css';
    }
}

function startReviewFromWorktree(path, branch) {
    const baseBranch = document.getElementById('base_branch')?.value || 'main';
    fetch('/api/reviews', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({repo_path: path, branch: branch, base_branch: baseBranch})
    })
    .then(r => r.json())
    .then(data => { window.location.href = '/review/' + data.id; });
}

function filterWorktrees(query) {
    const lower = query.toLowerCase();
    for (const item of document.querySelectorAll('#worktree-list .worktree-item')) {
        const text = item.getAttribute('data-search').toLowerCase();
        item.style.display = text.includes(lower) ? '' : 'none';
    }
}

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.wt-review-btn');
    if (!btn) return;
    const item = btn.closest('.worktree-item');
    if (!item) return;
    startReviewFromWorktree(item.dataset.wtPath, item.dataset.wtBranch);
});

document.addEventListener('DOMContentLoaded', () => {
    document.body.addEventListener('htmx:beforeRequest', (e) => {
        const elt = e.detail.elt;
        if (elt.classList.contains('line-num')) {
            const target = document.querySelector(elt.getAttribute('hx-target'));
            if (target) {
                target.querySelectorAll('.comment-form-wrapper').forEach(f => f.remove());
            }
        }
    });

    document.body.addEventListener('htmx:afterSwap', (e) => {
        const target = e.target;
        const emptyRow = target.closest('.comment-row-empty');
        if (emptyRow && target.children.length > 0) {
            emptyRow.style.display = '';
            emptyRow.classList.remove('comment-row-empty');
        }

        emptyRow || target.querySelectorAll('.comment-row-empty').forEach(row => {
            const thread = row.querySelector('.comment-thread');
            if (thread && thread.children.length > 0) {
                row.style.display = '';
                row.classList.remove('comment-row-empty');
            }
        });

        highlightDiffCode(target);
    });

    document.body.addEventListener('htmx:beforeRequest', (e) => {
        const elt = e.detail.elt;
        const wantsJson = (elt.getAttribute('hx-headers') || '').includes('application/json');

        if (wantsJson) {
            const form = elt.closest('form');
            if (form) {
                const formData = new FormData(form);
                const json = {};
                formData.forEach((value, key) => {
                    if (key === 'line_number') {
                        json[key] = parseInt(value);
                    } else if (key === 'resolved') {
                        json[key] = value === 'true';
                    } else {
                        json[key] = value;
                    }
                });
                e.detail.requestConfig.headers['Content-Type'] = 'application/json';
                e.detail.requestConfig.body = JSON.stringify(json);
                return;
            }

            const hxVals = elt.getAttribute('hx-vals');
            if (hxVals) {
                try {
                    const vals = JSON.parse(hxVals);
                    e.detail.requestConfig.headers['Content-Type'] = 'application/json';
                    e.detail.requestConfig.body = JSON.stringify(vals);
                } catch (_) {}
            }
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const openForms = document.querySelectorAll('.comment-form-wrapper');
            openForms.forEach(f => f.remove());
            const filter = document.querySelector('.file-filter');
            if (filter && document.activeElement === filter) {
                filter.value = '';
                filterFiles('');
                filter.blur();
            }
        }
    });
});

function highlightDiffCode(container) {
    if (typeof hljs === 'undefined') return;
    const fileName = container.querySelector?.('.diff-file-name')?.textContent || '';
    const lang = detectLanguage(fileName);
    if (!lang) return;

    container.querySelectorAll('.line-content code').forEach(el => {
        if (el.dataset.highlighted) return;
        const text = el.textContent;
        if (!text.trim()) return;
        try {
            const result = hljs.highlight(text, {language: lang, ignoreIllegals: true});
            el.innerHTML = result.value;
            el.dataset.highlighted = 'true';
        } catch (_) {}
    });
}

function detectLanguage(filename) {
    const ext = filename.split('.').pop()?.toLowerCase();
    const map = {
        'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
        'py': 'python', 'rb': 'ruby', 'rs': 'rust', 'go': 'go',
        'java': 'java', 'kt': 'kotlin', 'kts': 'kotlin', 'scala': 'scala',
        'cs': 'csharp', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
        'html': 'xml', 'htm': 'xml', 'xml': 'xml', 'vue': 'xml',
        'css': 'css', 'scss': 'scss', 'less': 'less',
        'json': 'json', 'yaml': 'yaml', 'yml': 'yaml', 'toml': 'ini',
        'sh': 'bash', 'bash': 'bash', 'zsh': 'bash',
        'sql': 'sql', 'md': 'markdown', 'dockerfile': 'dockerfile',
        'gradle': 'gradle', 'groovy': 'groovy',
        'swift': 'swift', 'dart': 'dart', 'php': 'php', 'lua': 'lua',
    };
    return map[ext] || null;
}

function toggleDiffView(btn) {
    const file = btn ? btn.closest('.diff-file') || btn.closest('.diff-file-card') : null;
    if (!file) return;
    const isInline = file.classList.toggle('diff-inline');
    if (btn) btn.textContent = isInline ? 'Unified' : 'Split';
}

function toggleComments(btn) {
    const file = btn.closest('.diff-file') || btn.closest('.diff-file-card');
    if (!file) return;
    const hidden = file.classList.toggle('comments-hidden');
    btn.textContent = hidden ? 'Show comments' : 'Hide comments';
}

function filterFiles(query) {
    const lower = query.toLowerCase();
    document.querySelectorAll('#file-list-items .file-item').forEach(item => {
        const path = (item.dataset.filePath || '').toLowerCase();
        item.style.display = path.includes(lower) ? '' : 'none';
    });
    document.querySelectorAll('.diff-file-card').forEach(card => {
        const path = (card.dataset.filepath || '').toLowerCase();
        card.style.display = path.includes(lower) ? '' : 'none';
    });
}

function toggleViewed(checkbox) {
    const item = checkbox.closest('.file-item');
    if (checkbox.checked) {
        item.classList.add('file-viewed');
    } else {
        item.classList.remove('file-viewed');
    }
    updateProgress();
}

function updateProgress() {
    const total = document.querySelectorAll('#file-list-items .file-item').length;
    const viewed = document.querySelectorAll('#file-list-items .file-viewed').length;
    const text = document.getElementById('progress-text');
    const fill = document.getElementById('progress-fill');
    if (text) text.textContent = `${viewed}/${total} viewed`;
    if (fill) fill.style.width = total ? `${(viewed / total) * 100}%` : '0%';
}
