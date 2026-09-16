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

async function goToBranchReview(repoPath, branch, baseBranch) {
    const searchResp = await fetch(
        '/api/reviews?repo_path=' + encodeURIComponent(repoPath)
        + '&branch=' + encodeURIComponent(branch) + '&limit=1'
    );
    const existing = await searchResp.json();
    if (existing && existing.length) {
        window.location.href = '/review/' + existing[0].id;
        return;
    }
    const resp = await fetch('/api/reviews', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({repo_path: repoPath, branch: branch, base_branch: baseBranch})
    });
    const data = await resp.json();
    window.location.href = '/review/' + data.id;
}

async function updateAllBranches(btn) {
    const repoPath = btn.dataset.repoPath;
    btn.disabled = true;
    btn.textContent = 'Updating...';
    try {
        const resp = await fetch('/api/stack/update-all', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({repo_path: repoPath})
        });
        const data = await resp.json();
        if (data.ok) {
            btn.textContent = 'Updated';
            btn.classList.add('stack-update-ok');
        } else {
            const failed = data.results.filter(r => !r.ok).map(r => r.branch);
            btn.textContent = failed.length ? 'Failed: ' + failed.join(', ') : 'Failed';
            btn.classList.add('stack-update-fail');
        }
        const container = btn.closest('.stack-map')?.parentElement;
        if (container) {
            const url = '/api/stack?repo_path=' + encodeURIComponent(repoPath);
            const html = await fetch(url).then(r => r.text());
            container.innerHTML = html;
        }
    } catch {
        btn.textContent = 'Error';
        btn.classList.add('stack-update-fail');
    }
}

async function updateStack(btn) {
    const repoPath = btn.dataset.repoPath;
    const stackId = btn.dataset.stackId;
    const stackEl = btn.closest('.registered-stack');
    btn.disabled = true;
    btn.textContent = 'Updating...';

    const branchEls = stackEl ? stackEl.querySelectorAll('.stack-branch') : [];
    branchEls.forEach(el => {
        el.classList.remove('rebase-ok', 'rebase-failed', 'rebase-active');
    });

    try {
        const resp = await fetch('/api/stack/update-stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({stack_id: stackId, repo_path: repoPath})
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = JSON.parse(line.slice(6));
                if (data.done) break;
                const branchEl = stackEl?.querySelector('.stack-branch[data-branch="' + data.branch + '"]');
                if (!branchEl) continue;
                if (data.status === 'rebasing') {
                    branchEl.classList.add('rebase-active');
                    btn.textContent = 'Rebasing ' + data.branch + '...';
                } else {
                    branchEl.classList.remove('rebase-active');
                    branchEl.classList.add(data.status === 'ok' ? 'rebase-ok' : 'rebase-failed');
                }
            }
        }

        btn.textContent = 'Done';
        btn.classList.add('stack-update-ok');
        setTimeout(async () => {
            const container = stackEl?.closest('.stack-map')?.parentElement || document.getElementById('stack-section');
            if (container) {
                const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
                container.innerHTML = html;
            }
        }, 1000);
    } catch {
        btn.textContent = 'Error';
        btn.classList.add('stack-update-fail');
    }
}

async function deleteStack(stackId, repoPath) {
    await fetch('/api/stacks/' + stackId, {method: 'DELETE'});
    const container = document.getElementById('stack-map-container') || document.getElementById('stack-section');
    if (container) {
        const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
        container.innerHTML = html;
    }
}

async function registerSuggestion(el, repoPath) {
    const chain = el.querySelector('.suggestion-chain').textContent;
    const branches = chain.split('→').map(s => s.trim()).filter(Boolean);
    branches.shift();
    const name = branches[branches.length - 1] || 'stack';
    const resp = await fetch('/api/stacks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, repo_path: repoPath, branches: branches})
    });
    if (resp.ok) {
        const container = document.getElementById('stack-map-container') || document.getElementById('stack-section');
        if (container) {
            const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
            container.innerHTML = html;
        }
    }
}

async function createStackManual(e, repoPath) {
    e.preventDefault();
    const form = e.target;
    const name = form.name.value;
    const select = form.branches;
    const branches = Array.from(select.selectedOptions).map(o => o.value);
    if (!branches.length) return;
    const resp = await fetch('/api/stacks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, repo_path: repoPath, branches: branches})
    });
    if (resp.ok) {
        const container = document.getElementById('stack-map-container') || document.getElementById('stack-section');
        if (container) {
            const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
            container.innerHTML = html;
        }
    }
}

async function addSidecar(e, stackId, repoPath) {
    e.preventDefault();
    const form = e.target;
    const parent = form.parent.value;
    const branch = form.branch.value;
    if (!parent || !branch) return;
    const resp = await fetch('/api/stacks/' + stackId + '/sidecars', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({parent: parent, branch: branch})
    });
    if (resp.ok) {
        const container = document.getElementById('stack-map-container') || document.getElementById('stack-section');
        if (container) {
            const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
            container.innerHTML = html;
        }
    }
}

async function removeSidecar(stackId, branch, repoPath) {
    const resp = await fetch('/api/stacks/' + stackId + '/sidecars/' + encodeURIComponent(branch), {
        method: 'DELETE'
    });
    if (resp.ok) {
        const container = document.getElementById('stack-map-container') || document.getElementById('stack-section');
        if (container) {
            const html = await fetch('/api/stack?repo_path=' + encodeURIComponent(repoPath)).then(r => r.text());
            container.innerHTML = html;
        }
    }
}

function filterWorktrees(query) {
    const lower = query.toLowerCase();
    for (const item of document.querySelectorAll('#worktree-list .worktree-item')) {
        const text = item.getAttribute('data-search').toLowerCase();
        item.style.display = text.includes(lower) ? '' : 'none';
    }
}

document.addEventListener('click', (e) => {
    const reviewBtn = e.target.closest('.wt-review-btn');
    if (reviewBtn) {
        const item = reviewBtn.closest('.worktree-item');
        if (item) startReviewFromWorktree(item.dataset.wtPath, item.dataset.wtBranch);
        return;
    }

    const updateBtn = e.target.closest('.wt-update-btn');
    if (updateBtn) {
        const item = updateBtn.closest('.worktree-item');
        if (!item) return;
        updateBtn.disabled = true;
        updateBtn.textContent = 'Updating...';
        updateBtn.classList.remove('wt-update-ok', 'wt-update-fail');
        fetch('/api/worktrees/rebase', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({worktree_path: item.dataset.wtPath})
        })
        .then(r => r.json())
        .then(data => {
            updateBtn.textContent = data.ok ? 'Updated' : 'Failed';
            updateBtn.classList.add(data.ok ? 'wt-update-ok' : 'wt-update-fail');
            if (!data.ok) updateBtn.title = data.message;
            if (data.ok) {
                const statsEl = item.querySelector('.wt-stats');
                if (statsEl) {
                    const repoSelect = document.getElementById('repo_select');
                    const repoPath = repoSelect ? repoSelect.value : '';
                    if (repoPath) {
                        fetch(`/api/worktrees?repo_path=${encodeURIComponent(repoPath)}`)
                            .then(r => r.text())
                            .then(html => {
                                document.getElementById('worktree-section').innerHTML = html;
                            });
                    }
                }
            }
            setTimeout(() => {
                updateBtn.disabled = false;
                updateBtn.textContent = 'Update';
                updateBtn.classList.remove('wt-update-ok', 'wt-update-fail');
                updateBtn.title = 'Rebase onto default branch';
            }, 3000);
        })
        .catch(() => {
            updateBtn.disabled = false;
            updateBtn.textContent = 'Update';
        });
    }
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('.stack-nav')) {
        document.querySelectorAll('.stack-nav.open').forEach(el => el.classList.remove('open'));
    }
});

document.addEventListener('click', (e) => {
    const node = e.target.closest('.branch-node[data-branch], .stack-graph-node[data-branch], .stack-graph-lane[data-branch], .stack-graph-branch-g[data-branch], .sg-branch-g[data-branch]');
    if (!node) return;
    if (e.target.closest('.registered-stack-actions')) return;
    goToBranchReview(node.dataset.repoPath, node.dataset.branch, node.dataset.base);
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

(function() {
    const el = document.getElementById('freshness-indicator');
    if (!el) return;
    const repoPath = el.dataset.repoPath;
    const branch = el.dataset.branch;
    const base = el.dataset.base;
    fetch('/api/stacks/branch-freshness?repo_path=' + encodeURIComponent(repoPath)
        + '&branch=' + encodeURIComponent(branch)
        + '&base=' + encodeURIComponent(base))
        .then(r => r.json())
        .then(data => {
            if (data.error) return;
            if (data.stale) {
                el.innerHTML = '<button class="freshness-btn freshness-stale" onclick="rebaseCurrent(this)">'
                    + data.behind + ' behind ' + base + ' &mdash; Update</button>';
            } else {
                el.innerHTML = '<span class="freshness-ok">Up to date</span>';
            }
        });
})();

async function rebaseCurrent(btn) {
    const el = document.getElementById('freshness-indicator');
    if (!el) return;
    btn.disabled = true;
    btn.textContent = 'Updating...';
    const resp = await fetch('/api/stacks/rebase-branch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            repo_path: el.dataset.repoPath,
            branch: el.dataset.branch,
            onto: el.dataset.base
        })
    });
    const data = await resp.json();
    if (data.ok) {
        el.innerHTML = '<span class="freshness-ok">Up to date</span>';
        location.reload();
    } else {
        btn.textContent = 'Failed: ' + (data.message || 'unknown error');
        btn.classList.add('freshness-failed');
    }
}
