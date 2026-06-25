
// ===== STATE =====
let autoClear = true, autoClearCancelled = true, skipDuplicates = true;
let completedGids = new Set(), cancelledGids = new Set(), pendingRemoval = new Set(), hiddenGids = new Set();
let previousStatus = {};
let activeNavLink = null;
let isTransitioning = false;

// ===== INIT =====
document.addEventListener("DOMContentLoaded", () => {
    activatePage();
    startPolling();
    loadStats();
    loadSites();
    
    // Initialize premium animations
    initCursorTracker();
    initNavIndicator();
    initCardTilts();
    initCustomDropdowns();
    initButtonRipples();
    setupAutocomplete();
    setupViewer();
});

// ===== CUSTOM PREMIUM DROPDOWNS =====
function initCustomDropdowns() {
    document.querySelectorAll('.toolbar-select').forEach(select => {
        // Hide the native select element
        select.style.display = 'none';
        
        // Check if custom container already exists (avoid double creation)
        let wrapper = document.getElementById(select.id + '-custom-container');
        if (wrapper) {
            wrapper.refreshOptions();
            return;
        }
        
        // Create custom wrapper container
        wrapper = document.createElement('div');
        wrapper.className = 'custom-select-container';
        wrapper.id = select.id + '-custom-container';
        
        // Create trigger button
        const trigger = document.createElement('div');
        trigger.className = 'custom-select-trigger';
        
        const labelText = document.createElement('span');
        labelText.className = 'custom-select-text';
        
        const arrow = document.createElement('i');
        arrow.className = 'fas fa-chevron-down custom-select-arrow';
        
        trigger.appendChild(labelText);
        trigger.appendChild(arrow);
        wrapper.appendChild(trigger);
        
        // Create options dropdown menu
        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'custom-select-options';
        wrapper.appendChild(optionsContainer);
        
        // Insert custom wrapper right after the native select
        select.parentNode.insertBefore(wrapper, select.nextSibling);
        
        // Open/Close toggle on click
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = wrapper.classList.contains('open');
            // Close all custom selects first
            document.querySelectorAll('.custom-select-container').forEach(c => {
                if (c !== wrapper) c.classList.remove('open');
            });
            wrapper.classList.toggle('open', !isOpen);
        });
        
        // Method to rebuild option list from native select options
        wrapper.refreshOptions = function() {
            optionsContainer.innerHTML = '';
            const selectedOption = select.options[select.selectedIndex];
            labelText.textContent = selectedOption ? selectedOption.textContent : '';
            
            Array.from(select.options).forEach(opt => {
                const optDiv = document.createElement('div');
                optDiv.className = 'custom-select-option';
                if (opt.value === select.value) {
                    optDiv.classList.add('selected');
                }
                optDiv.textContent = opt.textContent;
                optDiv.dataset.value = opt.value;
                
                optDiv.addEventListener('click', (e) => {
                    e.stopPropagation();
                    select.value = opt.value;
                    labelText.textContent = opt.textContent;
                    
                    // Update option highlight styling
                    optionsContainer.querySelectorAll('.custom-select-option').forEach(o => {
                        o.classList.toggle('selected', o.dataset.value === opt.value);
                    });
                    
                    wrapper.classList.remove('open');
                    
                    // Fire change event to run filters (onchange="applyGalleryFilters()")
                    select.dispatchEvent(new Event('change'));
                });
                
                optionsContainer.appendChild(optDiv);
            });
        };
        
        // Build for the first time
        wrapper.refreshOptions();
    });
    
    // Global click listener to close dropdowns when clicking outside
    document.addEventListener('click', () => {
        document.querySelectorAll('.custom-select-container').forEach(c => {
            c.classList.remove('open');
        });
    });
}

// ===== DYNAMIC BACKDROP & MOUSE GLOW =====
function initCursorTracker() {
    const glow = document.getElementById('cursorGlow');
    if (!glow) return;
    
    document.body.addEventListener('mousemove', (e) => {
        glow.style.left = e.clientX + 'px';
        glow.style.top = e.clientY + 'px';
        glow.style.opacity = '1';
    });
    
    document.body.addEventListener('mouseleave', () => {
        glow.style.opacity = '0';
    });
}

// ===== MAGIC SLIDING NAVIGATION PILL =====
function initNavIndicator() {
    const nav = document.querySelector('.nav');
    const indicator = document.getElementById('navIndicator');
    const links = document.querySelectorAll('.nav-link');
    if (!nav || !indicator) return;
    
    function snapToActive(immediate = false) {
        const activeLink = nav.querySelector('.nav-link.active');
        if (activeLink) {
            activeNavLink = activeLink;
            updateIndicator(activeLink, immediate);
        } else {
            indicator.style.opacity = '0';
        }
    }
    
    function updateIndicator(el, immediate = false) {
        if (immediate) {
            indicator.style.transition = 'none';
        } else {
            indicator.style.transition = 'transform 0.3s cubic-bezier(0.25, 1, 0.5, 1), height 0.3s ease, opacity 0.2s ease';
        }
        
        const navRect = nav.getBoundingClientRect();
        const elRect = el.getBoundingClientRect();
        const top = elRect.top - navRect.top;
        
        indicator.style.transform = `translateY(${top}px)`;
        indicator.style.height = `${elRect.height}px`;
        indicator.style.opacity = '1';
        
        if (immediate) {
            indicator.offsetHeight; // trigger reflow
            indicator.style.transition = '';
        }
    }
    
    links.forEach(link => {
        link.addEventListener('mouseenter', () => {
            updateIndicator(link);
        });
    });
    
    nav.addEventListener('mouseleave', () => {
        snapToActive();
    });
    
    setTimeout(() => snapToActive(true), 150);
    window.snapNavIndicator = snapToActive;
}

// ===== 3D CARD HOVER TILT & SHINE =====
function initCardTilts() {
    function ensureShine(card) {
        if (!card.querySelector('.card-shine')) {
            const shine = document.createElement('div');
            shine.className = 'card-shine';
            card.appendChild(shine);
        }
    }
    
    document.addEventListener('mousemove', (e) => {
        const card = e.target.closest('.stat-card, .site-card, .gallery-card, .card');
        if (!card) return;
        
        ensureShine(card);
        
        // Fast transition for move tracking
        card.style.transition = 'transform 0.08s cubic-bezier(0.25, 0.8, 0.25, 1), border-color var(--transition), box-shadow var(--transition)';
        
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        const rotateX = -((e.clientY - rect.top - centerY) / centerY) * 6;
        const rotateY = ((e.clientX - rect.left - centerX) / centerX) * 6;
        
        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-3px)`;
        card.style.setProperty('--shine-x', `${(x / rect.width) * 100}%`);
        card.style.setProperty('--shine-y', `${(y / rect.height) * 100}%`);
    });
    
    document.addEventListener('mouseout', (e) => {
        const card = e.target.closest('.stat-card, .site-card, .gallery-card, .card');
        if (!card) return;
        if (e.relatedTarget && card.contains(e.relatedTarget)) return;
        
        // Slow elastic spring back transition on leave
        card.style.transition = 'transform 0.6s cubic-bezier(0.25, 1.6, 0.5, 1)';
        card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px)';
    });
}

// ===== BUTTON CLICK RIPPLES =====
function initButtonRipples() {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-primary, .btn-secondary, .btn-danger, .theme-btn, .url-action, button:not(.toggle):not(.lightbox-close):not(.lightbox-nav)');
        if (!btn) return;
        
        btn.querySelectorAll('.btn-ripple').forEach(r => r.remove());
        
        const ripple = document.createElement('span');
        ripple.className = 'btn-ripple';
        
        const rect = btn.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        
        ripple.style.width = ripple.style.height = `${size}px`;
        ripple.style.left = `${x}px`;
        ripple.style.top = `${y}px`;
        
        btn.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    });
}


// ===== NUMERIC COUNT-UP HELPER =====
function animateCount(id, targetValue, suffix = '') {
    const el = document.getElementById(id);
    if (!el) return;
    
    let currentText = el.textContent.replace(suffix, '').trim();
    let startVal = parseFloat(currentText) || 0;
    let endVal = parseFloat(targetValue) || 0;
    
    if (startVal === endVal) {
        el.textContent = targetValue + (suffix ? ' ' + suffix : '');
        return;
    }
    
    const duration = 800;
    const startTime = performance.now();
    const isFloat = targetValue.toString().includes('.') || startVal.toString().includes('.');
    
    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3); // cubic ease out
        const current = startVal + (endVal - startVal) * ease;
        
        if (isFloat) {
            el.textContent = current.toFixed(1) + (suffix ? ' ' + suffix : '');
        } else {
            el.textContent = Math.floor(current) + (suffix ? ' ' + suffix : '');
        }
        
        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            el.textContent = targetValue + (suffix ? ' ' + suffix : '');
        }
    }
    requestAnimationFrame(update);
}

// ===== CONFETTI BURST ANIMATION =====
function triggerConfetti(gid) {
    const el = document.querySelector(`.progress-item[data-gid="${gid}"]`);
    if (!el) return;
    
    let container = el.querySelector('.confetti-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'confetti-container';
        el.appendChild(container);
    }
    
    const colors = ['#6c5ce7', '#a29bfe', '#00cec9', '#55efc4', '#ff7675', '#feca57'];
    const particleCount = 45;
    
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'confetti-particle';
        
        const angle = Math.random() * Math.PI * 2;
        const velocity = 60 + Math.random() * 120;
        const tx = Math.cos(angle) * velocity;
        const ty = Math.sin(angle) * velocity - 25;
        
        const size = 5 + Math.random() * 6;
        const color = colors[Math.floor(Math.random() * colors.length)];
        const duration = 0.7 + Math.random() * 0.7;
        
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.backgroundColor = color;
        particle.style.left = '50%';
        particle.style.top = '50%';
        particle.style.setProperty('--tx', `${tx}px`);
        particle.style.setProperty('--ty', `${ty}px`);
        particle.style.setProperty('--tr', `${360 + Math.random() * 360}deg`);
        particle.style.setProperty('--dur', `${duration}s`);
        
        container.appendChild(particle);
        setTimeout(() => particle.remove(), duration * 1000);
    }
    setTimeout(() => container.remove(), 1600);
}

// ===== NAVIGATION =====
function activatePage() {
    const path = location.pathname;
    const map = {'/':'downloads', '/downloads':'downloads', '/history':'history', '/gallery':'gallery', '/sites':'sites', '/settings':'settings', '/analytics':'analytics', '/discover':'discover', '/subscriptions':'subscriptions'};
    const page = map[path] || 'downloads';
    showPage(page);
}

function showPage(page) {
    if (page !== 'discover') {
        if (typeof closeAutocompleteDropdown === 'function') closeAutocompleteDropdown();
        if (typeof closeViewerModal === 'function') closeViewerModal();
    }
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById(page + 'Page');
    if (el) el.classList.add('active');

    document.querySelectorAll('.nav-link').forEach(l => {
        l.classList.toggle('active', l.dataset.page === page);
    });

    if (page === 'history') {
        const grid = document.querySelector('.history-grid');
        if (grid) {
            grid.classList.remove('animate');
            grid.offsetHeight;
            grid.classList.add('animate');
        }
        loadHistory();
    }
    if (page === 'gallery') {
        const grid = document.querySelector('.gallery-grid');
        if (grid) {
            grid.classList.remove('animate');
            grid.offsetHeight;
            grid.classList.add('animate');
        }
        loadGallery();
    }
    if (page === 'subscriptions') {
        loadSubscriptionsList();
    }
    if (page === 'discover') {
        syncDiscoverFormElements();
    }
    if (page === 'downloads') loadStats();
    if (page === 'analytics') loadAnalytics();
    
    if (window.snapNavIndicator) {
        window.snapNavIndicator();
    }
}

document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const page = link.dataset.page;
        showPage(page);
        history.pushState({}, '', page === 'downloads' ? '/' : '/' + page);
    });
});

window.addEventListener('popstate', activatePage);

// ===== ANALYTICS & CHARTS =====
let chartsStore = {
    platformShare: null,
    downloadTimeline: null
};

async function loadAnalytics() {
    try {
        const [statsRes, galleryRes] = await Promise.all([
            fetch('/stats'),
            fetch('/gallery-data')
        ]);
        const s = await statsRes.json();
        const galleries = await galleryRes.json();

        // 1. Metric Cards
        animateCount('anaStatStorage', s.total_size_mb, 'MB');
        
        const avgSize = s.total_galleries > 0 ? (s.total_size_mb / s.total_galleries).toFixed(1) : 0;
        animateCount('anaStatAvgSize', avgSize, 'MB');
        
        animateCount('anaStatImagesCount', s.total_images);
        
        const activePlatsCount = Object.values(s.platforms || {}).filter(v => v > 0).length;
        animateCount('anaStatDiversity', activePlatsCount);

        // Get theme colors dynamically
        const styles = getComputedStyle(document.documentElement);
        const accentColor = styles.getPropertyValue('--accent').trim() || '#6c5ce7';
        const accentColor2 = styles.getPropertyValue('--accent2').trim() || '#a29bfe';
        const accentRgb = styles.getPropertyValue('--accent-rgb').trim() || '108, 92, 231';

        // 2. Platform Share Donut Chart
        const platCanvas = document.getElementById('platformShareChart');
        if (platCanvas) {
            const platforms = s.platforms || {};
            const labels = [];
            const data = [];
            const backgroundColors = [];
            
            const siteColors = {
                imgbox: '#ff6b35', imgur: '#1bb76e', flickr: '#ff0084', pixiv: '#0096fa',
                danbooru: '#5b7bd5', gelbooru: '#006ffa', deviantart: '#05cc47', reddit: '#ff4500',
                tumblr: '#36465d', twitter: '#1da1f2', pinterest: '#bd081c', artstation: '#13aff0',
                generic: accentColor
            };

            Object.entries(platforms)
                .filter(([_, count]) => count > 0)
                .sort((a, b) => b[1] - a[1])
                .forEach(([plat, count]) => {
                    labels.push(plat.charAt(0).toUpperCase() + plat.slice(1));
                    data.push(count);
                    backgroundColors.push(siteColors[plat] || siteColors.generic);
                });

            if (chartsStore.platformShare) {
                chartsStore.platformShare.destroy();
            }

            if (data.length > 0) {
                chartsStore.platformShare = new Chart(platCanvas, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: data,
                            backgroundColor: backgroundColors,
                            borderWidth: 1,
                            borderColor: 'rgba(8, 9, 13, 0.8)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: {
                                    color: '#8b8fa3',
                                    font: { family: "'Inter', sans-serif", size: 11 },
                                    boxWidth: 10,
                                    padding: 12
                                }
                            },
                            tooltip: {
                                backgroundColor: '#11131c',
                                titleColor: '#e8eaf0',
                                bodyColor: '#8b8fa3',
                                borderColor: 'rgba(255,255,255,0.08)',
                                borderWidth: 1,
                                padding: 10,
                                displayColors: true,
                                boxWidth: 8,
                                boxHeight: 8
                            }
                        },
                        cutout: '70%'
                    }
                });
            } else {
                const ctx = platCanvas.getContext('2d');
                ctx.clearRect(0, 0, platCanvas.width, platCanvas.height);
                ctx.fillStyle = '#8b8fa3';
                ctx.font = '13px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('No platform data available', platCanvas.width / 2, platCanvas.height / 2);
            }
        }

        // 3. Download Timeline Chart (Area Chart)
        const timelineCanvas = document.getElementById('downloadTimelineChart');
        if (timelineCanvas) {
            const datesMap = {};
            galleries.forEach(g => {
                if (g.created) {
                    const dateStr = new Date(g.created * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                    datesMap[dateStr] = (datesMap[dateStr] || 0) + g.count;
                }
            });

            const sortedDates = Object.keys(datesMap).sort((a, b) => {
                const gA = galleries.find(g => new Date(g.created * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) === a);
                const gB = galleries.find(g => new Date(g.created * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) === b);
                return (gA?.created || 0) - (gB?.created || 0);
            });

            const timelineLabels = [];
            const timelineData = [];
            let cumulativeImages = 0;

            sortedDates.forEach(dateStr => {
                timelineLabels.push(dateStr);
                cumulativeImages += datesMap[dateStr];
                timelineData.push(cumulativeImages);
            });

            if (chartsStore.downloadTimeline) {
                chartsStore.downloadTimeline.destroy();
            }

            if (timelineData.length > 0) {
                const ctx = timelineCanvas.getContext('2d');
                const gradient = ctx.createLinearGradient(0, 0, 0, 240);
                gradient.addColorStop(0, `rgba(${accentRgb}, 0.25)`);
                gradient.addColorStop(1, `rgba(${accentRgb}, 0)`);

                chartsStore.downloadTimeline = new Chart(timelineCanvas, {
                    type: 'line',
                    data: {
                        labels: timelineLabels,
                        datasets: [{
                            label: 'Total Images',
                            data: timelineData,
                            borderColor: accentColor,
                            borderWidth: 2,
                            backgroundColor: gradient,
                            fill: true,
                            tension: 0.35,
                            pointBackgroundColor: accentColor,
                            pointBorderColor: '#08090d',
                            pointBorderWidth: 1.5,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: '#11131c',
                                titleColor: '#e8eaf0',
                                bodyColor: '#8b8fa3',
                                borderColor: 'rgba(255,255,255,0.08)',
                                borderWidth: 1,
                                padding: 10
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: '#8b8fa3', font: { family: "'Inter', sans-serif", size: 10 } }
                            },
                            y: {
                                grid: { color: 'rgba(255,255,255,0.03)' },
                                ticks: { color: '#8b8fa3', font: { family: "'Inter', sans-serif", size: 10 } }
                            }
                        }
                    }
                });
            } else {
                const ctx = timelineCanvas.getContext('2d');
                ctx.clearRect(0, 0, timelineCanvas.width, timelineCanvas.height);
                ctx.fillStyle = '#8b8fa3';
                ctx.font = '13px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('No history data available', timelineCanvas.width / 2, timelineCanvas.height / 2);
            }
        }

        // 4. Storage Cleanup Recommendations
        const cleanupContainer = document.getElementById('cleanupContainer');
        if (cleanupContainer) {
            const sortedGalleries = [...galleries].sort((a, b) => (b.size_mb || 0) - (a.size_mb || 0));
            const largeGalleries = sortedGalleries.filter(g => (g.size_mb || 0) > 0).slice(0, 5);

            if (largeGalleries.length === 0) {
                cleanupContainer.innerHTML = `<div class="empty-state"><i class="fas fa-circle-check" style="color:var(--success)"></i><p>Storage is clean and optimized!</p></div>`;
            } else {
                let html = '<div class="cleanup-list">';
                largeGalleries.forEach(g => {
                    const plat = g.platform || 'generic';
                    const date = g.created ? new Date(g.created * 1000).toLocaleDateString() : '';
                    html += `
                        <div class="cleanup-item" data-title="${esc(g.title)}">
                            <div class="cleanup-info">
                                <img class="cleanup-thumb" src="${g.thumbnail}" alt="" onerror="this.style.display='none'">
                                <div class="cleanup-meta">
                                    <h4>${esc(g.title)}</h4>
                                    <p><span class="gallery-plat-tag ${platClass(plat)}">${plat}</span> &bull; ${g.count} images &bull; ${date}</p>
                                </div>
                            </div>
                            <div class="cleanup-actions">
                                <span class="cleanup-size">${g.size_mb} MB</span>
                                <button class="btn-danger btn-sm" style="padding: 7px 10px; border-radius: 8px;" onclick="deleteGalleryFromCleanup('${esc(g.title)}')">
                                    <i class="fas fa-trash-can"></i>
                                </button>
                            </div>
                        </div>
                    `;
                });
                cleanupContainer.innerHTML = html + '</div>';
            }
        }

    } catch (e) {
        console.error("Failed to load analytics data", e);
    }
}

async function deleteGalleryFromCleanup(title) {
    if (!confirm(`Are you sure you want to delete "${title}"?\nThis will permanently delete all files in this gallery from your computer.`)) {
        return;
    }
    
    try {
        const res = await fetch('/delete-gallery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title })
        });
        const data = await res.json();
        
        if (data.ok) {
            notify(`Deleted ${title}`, 'success');
            
            const el = document.querySelector(`.cleanup-item[data-title="${title}"]`);
            if (el) {
                el.classList.add('slide-out');
                setTimeout(() => {
                    el.remove();
                    const list = document.querySelector('.cleanup-list');
                    if (list && !list.querySelector('.cleanup-item')) {
                        document.getElementById('cleanupContainer').innerHTML = `<div class="empty-state"><i class="fas fa-circle-check" style="color:var(--success)"></i><p>Storage is clean and optimized!</p></div>`;
                    }
                }, 350);
            }
            
            loadGallery();
            setTimeout(loadAnalytics, 400);
        } else {
            notify('Failed to delete folder', 'error');
        }
    } catch(e) {
        notify('Delete operation failed', 'error');
    }
}

// ===== STATS =====
async function loadStats() {
    try {
        const r = await fetch('/stats');
        const s = await r.json();
        animateCount('statGalleries', s.total_galleries);
        animateCount('statImages', s.total_images);
        animateCount('statActive', s.active_downloads);
        animateCount('statSize', s.total_size_mb, 'MB');

        // Render platform stats
        const container = document.getElementById('platformBarsContainer');
        const card = document.getElementById('platformAnalyticsCard');
        if (container && card) {
            const platforms = s.platforms || {};
            const total = Object.values(platforms).reduce((a, b) => a + b, 0);
            
            if (total > 0) {
                card.style.display = 'block';
                let html = '';
                
                const siteColors = {
                    imgbox: '#ff6b35', imgur: '#1bb76e', flickr: '#ff0084', pixiv: '#0096fa',
                    danbooru: '#5b7bd5', gelbooru: '#006ffa', deviantart: '#05cc47', reddit: '#ff4500',
                    tumblr: '#36465d', twitter: '#1da1f2', pinterest: '#bd081c', artstation: '#13aff0',
                    generic: '#6c5ce7'
                };
                
                const sortedPlats = Object.entries(platforms)
                    .filter(([_, count]) => count > 0)
                    .sort((a, b) => b[1] - a[1]);
                    
                sortedPlats.forEach(([plat, count]) => {
                    const pct = total > 0 ? (count / total * 100) : 0;
                    const color = siteColors[plat] || siteColors.generic;
                    html += `
                        <div class="platform-bar-item">
                            <div class="platform-bar-info">
                                <span class="platform-bar-label">
                                    <span class="site-dot" style="background:${color}"></span>
                                    ${plat}
                                </span>
                                <span style="color:var(--text-secondary)">${count} (${Math.round(pct)}%)</span>
                            </div>
                            <div class="platform-bar-bg">
                                <div class="platform-bar-fill" style="width: ${pct}%; background: ${color}"></div>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } else {
                card.style.display = 'none';
            }
        }
    } catch(e) {}
}

// ===== DOWNLOADS =====
function addExample() {
    document.getElementById('urlsInput').value = 'https://imgbox.com/g/sFtUwXoTrr\nhttps://imgur.com/gallery/abc123';
    notify('Example URLs added', 'success');
}
function clearUrls() {
    document.getElementById('urlsInput').value = '';
    notify('Cleared', 'success');
}

async function startDownload() {
    const urlsText = document.getElementById('urlsInput').value.trim();
    if (!urlsText) return notify('Enter at least one URL', 'error');

    let urls = [...new Set(urlsText.split(/[,\n]/).map(u => u.trim()).filter(Boolean))];
    if (!urls.length) return notify('No valid URLs', 'error');

    const btn = document.getElementById('downloadBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

    try {
        const r = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ urls: urls.join(','), skip_duplicates: skipDuplicates })
        });
        const data = await r.json();
        if (data.gids?.length) notify(`Started ${data.gids.length} download(s)`, 'success');
        if (data.skipped_count > 0) notify(`Skipped ${data.skipped_count} duplicate(s)`, 'warning');
        document.getElementById('urlsInput').value = '';
    } catch(e) {
        notify('Failed to start', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-rocket"></i> Start Download';
    }
}

async function checkDuplicates() {
    const text = document.getElementById('urlsInput').value.trim();
    if (!text) return notify('Enter URLs first', 'error');
    let urls = [...new Set(text.split(/[,\n]/).map(u => u.trim()).filter(Boolean).map(u => u.startsWith('http') ? u : 'https://' + u))];
    notify(`Checking ${urls.length} URL(s)...`, 'success');
    try {
        const r = await fetch('/check-duplicates', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({urls}) });
        const d = await r.json();
        const dupes = d.results.filter(r => r.exists);
        if (dupes.length) notify(`⚠ ${dupes.length} already downloaded`, 'warning');
        else notify(`✓ All ${urls.length} are new`, 'success');
    } catch(e) { notify('Check failed', 'error'); }
}

// ===== POLLING =====
function startPolling() {
    async function poll() {
        try {
            const r = await fetch('/status');
            const status = await r.json();

            for (const [gid, data] of Object.entries(status)) {
                const prev = previousStatus[gid];
                const done = data.status === 'Done', cancelled = data.status === 'Cancelled', skipped = data.status === 'Skipped (Already Downloaded)';

                if (done && !completedGids.has(gid) && prev?.status !== 'Done') {
                    completedGids.add(gid);
                    notify(`✓ ${data.title} completed (${data.total} images)`, 'success');
                    triggerConfetti(gid);
                    loadGallery();
                    
                    // Add bounce animation
                    const itemEl = document.querySelector(`.progress-item[data-gid="${gid}"]`);
                    if (itemEl) {
                        itemEl.classList.add('completed-pop');
                    }
                    
                    if (autoClear && !pendingRemoval.has(gid)) { pendingRemoval.add(gid); setTimeout(() => { removeItem(gid); pendingRemoval.delete(gid); }, 5000); }
                }
                if (cancelled && !cancelledGids.has(gid) && prev?.status !== 'Cancelled') {
                    cancelledGids.add(gid);
                    notify(`✗ ${data.title} cancelled`, 'warning');
                    if (autoClearCancelled && !pendingRemoval.has(gid)) { pendingRemoval.add(gid); setTimeout(() => { removeItem(gid); pendingRemoval.delete(gid); }, 3000); }
                }
                if (skipped && prev?.status !== data.status) {
                    notify(`⏭ ${data.title} skipped`, 'warning');
                    if (autoClear && !pendingRemoval.has(gid)) { pendingRemoval.add(gid); setTimeout(() => { removeItem(gid); pendingRemoval.delete(gid); }, 2000); }
                }
            }

            previousStatus = JSON.parse(JSON.stringify(status));
            renderProgress(status);
            loadStats();
        } catch(e) {}
        setTimeout(poll, 1000);
    }
    poll();
}

function platClass(p) { return 'plat-' + (p || 'generic'); }

function renderProgress(data) {
    const c = document.getElementById('progressContainer');
    const entries = Object.entries(data).filter(([gid]) => !hiddenGids.has(gid));
    if (!entries.length) { c.innerHTML = '<div class="empty-state"><i class="fas fa-cloud-arrow-down"></i><p>No active downloads</p></div>'; return; }

    for (const [gid, d] of entries) {
        const pct = d.total > 0 ? (d.done / d.total * 100) : 0;
        const s = d.status || 'Pending';
        const p = d.platform || 'generic';
        const isDone = s === 'Done', isCancelled = s === 'Cancelled', isSkipped = s.includes('Skipped'), isError = s === 'Error' || s === 'No images found';

        let badgeHtml = '';
        if (isDone) badgeHtml = '<span class="badge complete">✓ Done</span>';
        else if (isCancelled) badgeHtml = '<span class="badge cancelled">✗ Cancelled</span>';
        else if (isSkipped) badgeHtml = '<span class="badge skipped">⏭ Skipped</span>';
        else if (isError) badgeHtml = '<span class="badge error">! Error</span>';
        else badgeHtml = `<span class="platform-badge ${platClass(p)}">${p}</span><span class="status-pulse-dot" title="Downloading..."></span>`;

        const fillClass = isDone ? 'complete' : (isCancelled ? 'cancelled' : '');
        const controls = (!isDone && !isCancelled && !isSkipped && !isError) ? `
            <div class="progress-controls">
                <button class="btn-secondary btn-sm" onclick="controlDl('${gid}','pause')"><i class="fas fa-pause"></i> Pause</button>
                <button class="btn-secondary btn-sm" onclick="controlDl('${gid}','resume')"><i class="fas fa-play"></i> Resume</button>
                <button class="btn-danger btn-sm" onclick="controlDl('${gid}','cancel')"><i class="fas fa-xmark"></i> Cancel</button>
            </div>` : '';

        let existing = c.querySelector(`[data-gid="${gid}"]`);
        if (existing) {
            const fill = existing.querySelector('.fill');
            if (fill) { fill.style.width = (isDone||isSkipped ? 100 : pct) + '%'; fill.className = 'fill ' + fillClass; }
            const count = existing.querySelector('.progress-count');
            if (count) count.textContent = d.done + '/' + d.total;
            const statusEl = existing.querySelector('.progress-status span');
            if (statusEl) statusEl.textContent = s;
            const pctEl = existing.querySelectorAll('.progress-status span')[1];
            if (pctEl) pctEl.textContent = Math.round(pct) + '%';
            const titleArea = existing.querySelector('.progress-title');
            if (titleArea) titleArea.innerHTML = '<span>' + esc(d.title || 'Gallery') + '</span>' + badgeHtml;
            const ctrlArea = existing.querySelector('.progress-controls');
            if (isDone || isCancelled || isSkipped || isError) { if (ctrlArea) ctrlArea.remove(); }
        } else {
            const emptyState = c.querySelector('.empty-state');
            if (emptyState) emptyState.remove();
            const div = document.createElement('div');
            div.className = 'progress-item';
            div.setAttribute('data-gid', gid);
            div.innerHTML = `
                <button class="remove-btn" onclick="removeItem('${gid}')" title="Remove">✕</button>
                <div class="progress-header">
                    <div class="progress-title"><span>${esc(d.title || 'Gallery')}</span>${badgeHtml}</div>
                    <span class="progress-count">${d.done}/${d.total}</span>
                </div>
                <div class="bar"><div class="fill ${fillClass}" style="width:${isDone||isSkipped ? 100 : pct}%"></div></div>
                <div class="progress-status"><span>${s}</span><span>${Math.round(pct)}%</span></div>
                ${controls}`;
            c.appendChild(div);
        }
    }
}

async function controlDl(gid, action) {
    try {
        await fetch('/control', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({id: gid, action}) });
        if (action === 'pause') notify('Paused', 'success');
        else if (action === 'resume') notify('Resumed', 'success');
        else if (action === 'cancel') { notify('Cancelling...', 'warning'); setTimeout(() => removeItem(gid), 1000); }
    } catch(e) { notify('Control failed', 'error'); }
}

async function removeItem(gid) {
    hiddenGids.add(gid);
    const el = document.querySelector(`.progress-item[data-gid="${gid}"]`);
    if (el) { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; el.style.transition = '0.3s'; setTimeout(() => { el.remove(); const c = document.getElementById('progressContainer'); if (!c.querySelector('.progress-item')) c.innerHTML = '<div class="empty-state"><i class="fas fa-cloud-arrow-down"></i><p>No active downloads</p></div>'; }, 300); }
    try { await fetch('/control', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({id: gid, action: 'remove'}) }); } catch(e) {}
    loadHistory();
}

function clearAllDownloads() {
    if (!confirm('Clear all downloads from list?')) return;
    fetch('/status').then(r => r.json()).then(data => {
        Object.keys(data).forEach(gid => removeItem(gid));
        notify('Cleared all', 'success');
    });
}

// ===== HISTORY =====
let historyCache = null;

async function loadHistory() {
    try {
        const r = await fetch('/history-data');
        const data = await r.json();
        
        if (historyCache && JSON.stringify(historyCache) === JSON.stringify(data)) {
            return;
        }
        historyCache = data;
        
        const c = document.getElementById('historyContainer');
        if (!data.length) { c.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>No downloads yet</p></div>'; return; }
        let html = '<div class="history-grid animate">';
        data.forEach(item => {
            html += `<div class="history-item">
                <div><div class="history-title">${esc(item.title)}</div><div class="history-count">${item.count} images</div></div>
                <div class="history-meta">
                    <span class="history-platform ${platClass(item.platform)}">${item.platform || 'generic'}</span>
                    <span style="font-size:11px;color:var(--text-secondary)">📁 ${esc(item.folder)}</span>
                </div>
            </div>`;
        });
        c.innerHTML = html + '</div>';
    } catch(e) {}
}

// ===== GALLERY =====
let galleryCache = null;

async function loadGallery() {
    try {
        const r = await fetch('/gallery-data');
        const data = await r.json();
        
        if (galleryCache && JSON.stringify(galleryCache) === JSON.stringify(data)) {
            return;
        }
        galleryCache = data;
        populatePlatformFilter();
        applyGalleryFilters();
    } catch(e) {}
}

function populatePlatformFilter() {
    const sel = document.getElementById('galPlatform');
    const current = sel.value;
    const platforms = [...new Set(galleryCache.map(g => g.platform || 'generic'))].sort();
    sel.innerHTML = '<option value="all">All Platforms</option>';
    platforms.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p.charAt(0).toUpperCase() + p.slice(1);
        sel.appendChild(opt);
    });
    sel.value = current || 'all';
    
    // Sync with custom dropdown
    const customContainer = document.getElementById('galPlatform-custom-container');
    if (customContainer && customContainer.refreshOptions) {
        customContainer.refreshOptions();
    }
}

function applyGalleryFilters() {
    const sortVal = document.getElementById('galSort').value;
    const platVal = document.getElementById('galPlatform').value;
    const searchVal = document.getElementById('galSearch')?.value.trim().toLowerCase() || '';
    let data = [...galleryCache];

    // Filter by platform
    if (platVal !== 'all') data = data.filter(g => (g.platform || 'generic') === platVal);

    // Filter by search query
    if (searchVal) {
        data = data.filter(g => (g.title || '').toLowerCase().includes(searchVal));
    }

    // Sort
    const [key, dir] = sortVal.split('-');
    data.sort((a, b) => {
        let va, vb;
        if (key === 'date') { va = a.created || 0; vb = b.created || 0; }
        else if (key === 'name') { va = (a.title || '').toLowerCase(); vb = (b.title || '').toLowerCase(); }
        else if (key === 'count') { va = a.count || 0; vb = b.count || 0; }
        else if (key === 'size') { va = a.size_mb || 0; vb = b.size_mb || 0; }
        if (typeof va === 'string') return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        return dir === 'asc' ? va - vb : vb - va;
    });

    document.getElementById('galCount').textContent = data.length + ' galler' + (data.length === 1 ? 'y' : 'ies');
    renderGalleryCards(data);
}

function renderGalleryCards(data) {
    const c = document.getElementById('galleryContainer');
    if (!data.length) { c.innerHTML = '<div class="empty-state"><i class="fas fa-photo-film"></i><p>No galleries match your filters</p></div>'; return; }
    let html = '<div class="gallery-grid animate">';
    data.forEach((g, idx) => {
        const date = g.created ? new Date(g.created * 1000).toLocaleDateString() : '';
        const plat = g.platform || 'generic';
        // Convert the stringified object so we can pass it safely
        const encodedG = encodeURIComponent(JSON.stringify(g));
        html += `<div class="gallery-card" onclick="openLightbox(decodeURIComponent('${encodedG}'))">
            <div class="gallery-thumb-container">
                <img class="gallery-thumb" src="${g.thumbnail}" alt="${esc(g.title)}" loading="lazy" onerror="this.style.display='none'">
                <div class="gallery-card-actions">
                    <button class="gallery-card-action-btn" onclick="openFolder(event, '${esc(g.title)}')" title="Open Folder"><i class="fas fa-folder-open"></i></button>
                    <button class="gallery-card-action-btn delete" onclick="deleteGallery(event, '${esc(g.title)}')" title="Delete Gallery"><i class="fas fa-trash-can"></i></button>
                </div>
            </div>
            <div class="gallery-info">
                <h4>${esc(g.title)}</h4>
                <div class="gallery-info-meta"><span>${g.count} images</span><span>${g.size_mb} MB</span></div>
                <div class="gallery-info-meta" style="margin-top:4px"><span class="gallery-plat-tag ${platClass(plat)}">${plat}</span><span style="color:var(--muted)">${date}</span></div>
            </div>
        </div>`;
    });
    c.innerHTML = html + '</div>';
}

async function openFolder(event, title) {
    if (event) event.stopPropagation();
    try {
        const res = await fetch('/open-folder', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title })
        });
        const data = await res.json();
        if (data.ok) {
            notify(`Opened folder for "${title}"`, 'success');
        } else {
            notify(`Failed to open folder: ${data.error}`, 'error');
        }
    } catch(e) {
        notify('Failed to open folder', 'error');
    }
}

async function deleteGallery(event, title) {
    if (event) event.stopPropagation();
    if (!confirm(`Are you sure you want to delete "${title}"?\nThis will permanently delete all files in this gallery from your computer.`)) {
        return;
    }
    
    try {
        const res = await fetch('/delete-gallery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title })
        });
        const data = await res.json();
        
        if (data.ok) {
            notify(`Deleted "${title}"`, 'success');
            
            // Find card and animate removal
            const cards = document.querySelectorAll('.gallery-card');
            for (const card of cards) {
                if (card.querySelector('h4')?.textContent === title) {
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.9) translateY(10px)';
                    card.style.transition = '0.35s cubic-bezier(0.4, 0, 0.2, 1)';
                    setTimeout(() => {
                        card.remove();
                        loadGallery();
                        loadStats();
                    }, 350);
                    break;
                }
            }
        } else {
            notify('Failed to delete folder', 'error');
        }
    } catch(e) {
        notify('Delete operation failed', 'error');
    }
}

// ===== LIGHTBOX =====
let lbImages = [];
let lbIndex = 0;
let isSwipeInit = false;
let touchStartX = 0;
let touchEndX = 0;

function openLightbox(galleryJson) {
    const g = JSON.parse(galleryJson);
    if (!g.images || !g.images.length) return;
    
    lbImages = g.images;
    lbIndex = 0;
    isTransitioning = false;
    
    document.getElementById('lightboxTitle').textContent = g.title;
    
    // Bind actions
    const openFolderBtn = document.getElementById('lightboxOpenFolderBtn');
    if (openFolderBtn) {
        openFolderBtn.onclick = (e) => openFolder(e, g.title);
    }
    const deleteBtn = document.getElementById('lightboxDeleteBtn');
    if (deleteBtn) {
        deleteBtn.onclick = (e) => {
            if (confirm(`Are you sure you want to delete "${g.title}"?\nThis will permanently delete all files in this gallery from your computer.`)) {
                deleteGallery(e, g.title);
                closeLightbox();
            }
        };
    }
    
    const img = document.getElementById('lightboxImg');
    img.className = '';
    img.src = lbImages[0];
    document.getElementById('lightboxCounter').textContent = `1 / ${lbImages.length}`;
    
    const thumbsContainer = document.getElementById('lightboxThumbnailsContainer');
    const counterEl = document.getElementById('lightboxCounter');
    
    if (lbImages.length <= 1) {
        if (thumbsContainer) thumbsContainer.style.display = 'none';
        if (counterEl) counterEl.style.display = 'none';
        document.querySelectorAll('.lightbox-nav').forEach(btn => btn.style.display = 'none');
    } else {
        if (thumbsContainer) thumbsContainer.style.display = 'flex';
        if (counterEl) counterEl.style.display = 'block';
        document.querySelectorAll('.lightbox-nav').forEach(btn => btn.style.display = 'flex');
    }
    
    renderLightboxThumbnails();
    initLightboxSwipe();
    
    const lb = document.getElementById('lightbox');
    lb.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    document.getElementById('lightbox').classList.remove('active');
    document.body.style.overflow = '';
    setTimeout(() => {
        document.getElementById('lightboxImg').src = '';
    }, 300);
}

function changeLightboxImg(newIndex) {
    if (isTransitioning || newIndex === lbIndex || newIndex < 0 || newIndex >= lbImages.length) return;
    isTransitioning = true;
    
    const img = document.getElementById('lightboxImg');
    const direction = newIndex > lbIndex ? 'next' : 'prev';
    const nextIndex = newIndex;
    
    const outClass = direction === 'next' ? 'slide-out-left' : 'slide-out-right';
    const inClass = direction === 'next' ? 'slide-in-right' : 'slide-in-left';
    
    img.className = outClass;
    
    setTimeout(() => {
        lbIndex = nextIndex;
        img.src = lbImages[lbIndex];
        
        img.onload = () => {
            img.className = inClass;
            document.getElementById('lightboxCounter').textContent = `${lbIndex + 1} / ${lbImages.length}`;
            updateActiveThumbnail();
            
            setTimeout(() => {
                img.className = '';
                isTransitioning = false;
            }, 350);
        };
        
        if (lbIndex < lbImages.length - 1) {
            new Image().src = lbImages[lbIndex + 1];
        }
        if (lbIndex > 0) {
            new Image().src = lbImages[lbIndex - 1];
        }
    }, 150);
}

function prevLightboxImage() {
    let target = lbIndex > 0 ? lbIndex - 1 : lbImages.length - 1;
    if (target === lbIndex) return;
    changeLightboxImg(target);
}

function nextLightboxImage() {
    let target = lbIndex < lbImages.length - 1 ? lbIndex + 1 : 0;
    if (target === lbIndex) return;
    changeLightboxImg(target);
}

function renderLightboxThumbnails() {
    const container = document.getElementById('lightboxThumbnails');
    if (!container) return;
    
    container.innerHTML = '';
    lbImages.forEach((src, idx) => {
        const thumb = document.createElement('img');
        thumb.src = src;
        thumb.className = 'lightbox-thumb' + (idx === lbIndex ? ' active' : '');
        thumb.alt = `Thumb ${idx + 1}`;
        thumb.loading = 'lazy';
        thumb.onclick = (e) => {
            e.stopPropagation();
            changeLightboxImg(idx);
        };
        container.appendChild(thumb);
    });
    
    updateActiveThumbnail(true);
}

function updateActiveThumbnail(immediate = false) {
    const container = document.getElementById('lightboxThumbnails');
    if (!container) return;
    
    const thumbs = container.querySelectorAll('.lightbox-thumb');
    thumbs.forEach((t, idx) => {
        t.classList.toggle('active', idx === lbIndex);
    });
    
    const activeThumb = thumbs[lbIndex];
    if (activeThumb) {
        if (immediate) {
            container.scrollLeft = activeThumb.offsetLeft - (container.clientWidth / 2) + (activeThumb.clientWidth / 2);
        } else {
            container.scrollTo({
                left: activeThumb.offsetLeft - (container.clientWidth / 2) + (activeThumb.clientWidth / 2),
                behavior: 'smooth'
            });
        }
    }
}

function initLightboxSwipe() {
    if (isSwipeInit) return;
    const wrapper = document.getElementById('lightboxImgWrapper');
    if (!wrapper) return;
    
    wrapper.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });
    
    wrapper.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });
    
    isSwipeInit = true;
}

function handleSwipe() {
    const diff = touchEndX - touchStartX;
    if (Math.abs(diff) > 50) {
        if (diff > 0) {
            prevLightboxImage();
        } else {
            nextLightboxImage();
        }
    }
}

document.addEventListener('keydown', e => {
    if (!document.getElementById('lightbox').classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') prevLightboxImage();
    if (e.key === 'ArrowRight') nextLightboxImage();
});

// ===== SITES =====
async function loadSites() {
    try {
        const r = await fetch('/supported-sites');
        const sites = await r.json();
        const c = document.getElementById('sitesGrid');
        let html = '';
        for (const [key, info] of Object.entries(sites)) {
            const favicon = info.domain ? `<img class="site-favicon" src="https://www.google.com/s2/favicons?domain=${info.domain}&sz=32" alt="">` : '<span class="site-dot" style="background:' + info.color + '"></span>';
            const linkOpen = info.url ? `<a href="${info.url}" target="_blank" rel="noopener" class="site-card-link">` : '<div class="site-card-link">';
            const linkClose = info.url ? '</a>' : '</div>';
            const linkLabel = info.domain ? `<span class="site-url">${info.domain} <i class="fas fa-arrow-up-right-from-square"></i></span>` : '';
            html += `${linkOpen}<div class="site-card" style="--c:${info.color}">
                <div style="position:absolute;top:0;left:0;right:0;height:3px;background:${info.color};border-radius:var(--radius) var(--radius) 0 0"></div>
                <h4>${favicon}${info.name}</h4>
                <p>${info.desc}</p>
                ${linkLabel}
            </div>${linkClose}`;
        }
        c.innerHTML = html;
    } catch(e) {}
}

// ===== SETTINGS =====
function toggleSetting(key) {
    if (key === 'skip') { skipDuplicates = !skipDuplicates; document.getElementById('toggleSkip').classList.toggle('active', skipDuplicates); }
    else if (key === 'autoClear') { autoClear = !autoClear; document.getElementById('toggleAutoClear').classList.toggle('active', autoClear); }
    else if (key === 'autoClearCancelled') { autoClearCancelled = !autoClearCancelled; document.getElementById('toggleAutoClearCancelled').classList.toggle('active', autoClearCancelled); }
    notify(`Setting updated`, 'success');
}

function setTheme(btn, rgb, acc1, acc2) {
    document.documentElement.style.setProperty('--accent-rgb', rgb);
    document.documentElement.style.setProperty('--accent', acc1);
    document.documentElement.style.setProperty('--accent2', acc2);
    
    document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    notify('Theme changed successfully');
    
    if (document.getElementById('analyticsPage').classList.contains('active')) {
        loadAnalytics();
    }
}

// ===== DISCOVER =====
// ===== DISCOVER BOORU STATE =====
let discoverQuery = "";
let discoverPlatforms = ["danbooru", "gelbooru"];
let discoverPage = 1;
let discoverResults = [];
let discoverLoading = false;
let discoverSafeMode = true;

function syncDiscoverFormElements() {
    const input = document.getElementById('discoverSearchInput');
    if (input) input.value = discoverQuery;
    
    const cbDan = document.getElementById('cb-danbooru');
    if (cbDan) cbDan.checked = discoverPlatforms.includes('danbooru');
    
    const cbGel = document.getElementById('cb-gelbooru');
    if (cbGel) cbGel.checked = discoverPlatforms.includes('gelbooru');

    const toggleSafe = document.getElementById('toggleDiscoverSafe');
    if (toggleSafe) {
        toggleSafe.classList.toggle('active', discoverSafeMode);
    }
    
    const label = document.getElementById('safeModeLabel');
    const helper = document.getElementById('discoverHelperText');
    if (discoverSafeMode) {
        if (label) {
            label.textContent = "Safe Mode";
            label.style.color = "var(--text-secondary)";
        }
        if (helper) helper.textContent = "Searches use booru tag syntax. Safe posts only.";
    } else {
        if (label) {
            label.textContent = "Unsafe Mode";
            label.style.color = "var(--error)";
        }
        if (helper) helper.textContent = "Searches use booru tag syntax. Questionable and explicit results allowed.";
    }
}

function toggleDiscoverSafeMode() {
    discoverSafeMode = !discoverSafeMode;
    syncDiscoverFormElements();
}

function handleDiscoverSearch() {
    if (typeof closeAutocompleteDropdown === 'function') {
        closeAutocompleteDropdown();
    }
    if (discoverLoading) return;
    
    const input = document.getElementById('discoverSearchInput');
    const query = input ? input.value.trim() : "";
    
    if (!query) {
        notify("Please enter tags or keywords to search", "error");
        return;
    }
    
    const platforms = [];
    if (document.getElementById('cb-danbooru').checked) platforms.push('danbooru');
    if (document.getElementById('cb-gelbooru').checked) platforms.push('gelbooru');
    
    if (platforms.length === 0) {
        notify("Please select at least one source (Danbooru or Gelbooru)", "error");
        return;
    }
    
    discoverQuery = query;
    discoverPlatforms = platforms;
    discoverPage = 1;
    discoverResults = [];
    
    fetchDiscoverResults(false);
}

function loadMoreDiscover() {
    if (discoverLoading) return;
    discoverPage += 1;
    fetchDiscoverResults(true);
}

async function fetchDiscoverResults(append = false) {
    discoverLoading = true;
    
    const searchBtn = document.getElementById('discoverSearchBtn');
    const loadMoreBtn = document.getElementById('discoverLoadMoreBtn');
    const container = document.getElementById('discoverContainer');
    const summaryArea = document.getElementById('discoverSummaryArea');
    const errorChips = document.getElementById('discoverErrorChips');
    
    if (searchBtn) {
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
    }
    if (loadMoreBtn) {
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    }
    
    if (!append) {
        summaryArea.textContent = "";
        errorChips.innerHTML = "";
        // Show skeleton loaders
        container.innerHTML = "";
        for (let i = 0; i < 8; i++) {
            const skeleton = document.createElement('div');
            skeleton.className = 'gallery-card skeleton-card';
            skeleton.innerHTML = `
                <div class="gallery-thumb-container skeleton-thumb"></div>
                <div class="gallery-info">
                    <div class="skeleton-line skeleton-title"></div>
                    <div class="skeleton-line skeleton-meta"></div>
                    <div class="skeleton-line skeleton-tags"></div>
                </div>
            `;
            container.appendChild(skeleton);
        }
    }
    
    try {
        const params = new URLSearchParams({
            q: discoverQuery,
            sources: discoverPlatforms.join(','),
            page: discoverPage.toString(),
            limit: "20",
            safe_mode: discoverSafeMode ? "true" : "false"
        });
        
        const res = await fetch('/api/discover/booru-search?' + params.toString());
        if (!res.ok && res.status !== 429) {
            throw new Error(`Server returned HTTP ${res.status}`);
        }
        
        const data = await res.json();
        
        if (data.error) {
            notify(data.message || "Search failed", "error");
            if (!append) {
                container.innerHTML = `<div class="empty-state"><i class="fas fa-circle-exclamation" style="color:var(--error)"></i><p>${esc(data.message)}</p></div>`;
            }
            return;
        }
        
        const newResults = data.results || [];
        
        // Filter duplicates
        const existingKeys = new Set(discoverResults.map(r => `${r.source}_${r.post_id}`));
        const filteredNewResults = [];
        for (const item of newResults) {
            const key = `${item.source}_${item.post_id}`;
            if (!existingKeys.has(key)) {
                existingKeys.add(key);
                filteredNewResults.push(item);
            }
        }
        
        if (append) {
            discoverResults = discoverResults.concat(filteredNewResults);
        } else {
            discoverResults = filteredNewResults;
        }
        
        // Render error chips
        errorChips.innerHTML = "";
        if (data.errors && data.errors.length > 0) {
            data.errors.forEach(err => {
                const chip = document.createElement('div');
                chip.className = 'error-chip';
                
                const icon = document.createElement('i');
                icon.className = 'fas fa-triangle-exclamation';
                chip.appendChild(icon);
                
                const label = document.createElement('strong');
                label.textContent = `${err.source.charAt(0).toUpperCase() + err.source.slice(1)}: `;
                chip.appendChild(label);
                
                const text = document.createElement('span');
                text.textContent = err.message || "Source offline";
                chip.appendChild(text);
                
                errorChips.appendChild(chip);
                notify(`${err.source} error: ${err.message}`, "warning");
            });
        }
        
        renderDiscoverGrid(discoverResults);
        
        // Update summary text
        summaryArea.textContent = `Showing ${discoverResults.length} posts for "${discoverQuery}"`;
        
        // Determine has_more
        const anyMore = data.has_more ? Object.values(data.has_more).some(v => v === true) : false;
        const loadMoreContainer = document.querySelector('#discoverPage .load-more-container');
        if (loadMoreContainer) {
            loadMoreContainer.style.display = anyMore ? 'flex' : 'none';
        }
        
    } catch(e) {
        notify("Search failed due to connection error", "error");
        if (!append) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-circle-xmark" style="color:var(--error)"></i><p>Search failed due to a connection issue.</p></div>';
        }
    } finally {
        discoverLoading = false;
        if (searchBtn) {
            searchBtn.disabled = false;
            searchBtn.innerHTML = '<i class="fas fa-magnifying-glass"></i> Search';
        }
        if (loadMoreBtn) {
            loadMoreBtn.disabled = false;
            loadMoreBtn.innerHTML = '<i class="fas fa-circle-chevron-down"></i> Load More';
        }
    }
}

function renderDiscoverGrid(results) {
    const container = document.getElementById('discoverContainer');
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-face-frown"></i><p>No safe posts found for this tag search.</p></div>';
        return;
    }
    
    container.innerHTML = "";
    const grid = document.createElement('div');
    grid.className = 'gallery-grid animate';
    
    results.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'gallery-card search-result-card';
        card.setAttribute('tabindex', '0');
        card.setAttribute('role', 'button');
        card.setAttribute('aria-label', `${item.source_label} post ${item.post_id}. Press Enter or Space to open viewer.`);
        
        card.addEventListener('click', (e) => {
            // Do not open viewer if clicking on pills or action links
            if (e.target.closest('.tag-pill') || e.target.closest('.gallery-card-action-btn') || e.target.closest('a')) {
                return;
            }
            openViewerModal(index);
        });
        
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openViewerModal(index);
            }
        });
        
        const thumbContainer = document.createElement('div');
        thumbContainer.className = 'gallery-thumb-container';
        
        const img = document.createElement('img');
        img.className = 'gallery-thumb';
        if (item.source === "gelbooru") {
            img.src = `/api/proxy-image?url=${encodeURIComponent(item.preview_url)}`;
        } else {
            img.src = item.preview_url;
        }
        img.alt = item.title || 'Artwork';
        img.loading = 'lazy';
        
        img.onerror = () => {
            img.style.display = 'none';
            const placeholder = document.createElement('div');
            placeholder.className = 'thumb-placeholder';
            
            const pIcon = document.createElement('i');
            pIcon.className = 'fas fa-image';
            placeholder.appendChild(pIcon);
            
            const pText = document.createElement('span');
            pText.textContent = "Preview Unavailable";
            placeholder.appendChild(pText);
            
            thumbContainer.appendChild(placeholder);
        };
        thumbContainer.appendChild(img);
        
        const actions = document.createElement('div');
        actions.className = 'gallery-card-actions';
        
        const linkBtn = document.createElement('a');
        linkBtn.className = 'gallery-card-action-btn';
        linkBtn.href = item.post_url;
        linkBtn.target = '_blank';
        linkBtn.rel = 'noopener noreferrer';
        linkBtn.setAttribute('aria-label', `Open original ${item.source_label} post`);
        linkBtn.addEventListener('click', e => e.stopPropagation());
        
        const linkIcon = document.createElement('i');
        linkIcon.className = 'fas fa-arrow-up-right-from-square';
        linkBtn.appendChild(linkIcon);
        actions.appendChild(linkBtn);
        thumbContainer.appendChild(actions);
        card.appendChild(thumbContainer);
        
        const info = document.createElement('div');
        info.className = 'gallery-info';
        
        const title = document.createElement('h4');
        title.textContent = item.title || `${item.source_label} Post ${item.post_id}`;
        info.appendChild(title);
        
        const badgesContainer = document.createElement('div');
        badgesContainer.className = 'card-meta-badges';
        
        const sourceBadge = document.createElement('span');
        sourceBadge.className = `gallery-plat-tag ${platClass(item.source)}`;
        sourceBadge.textContent = item.source_label;
        badgesContainer.appendChild(sourceBadge);
        
        const ratingBadge = document.createElement('span');
        ratingBadge.className = 'meta-badge rating-safe';
        ratingBadge.textContent = 'Safe';
        badgesContainer.appendChild(ratingBadge);
        
        if (item.width && item.height) {
            const dimsBadge = document.createElement('span');
            dimsBadge.className = 'meta-badge dimensions-badge';
            dimsBadge.textContent = `${item.width} x ${item.height}`;
            badgesContainer.appendChild(dimsBadge);
        }
        
        if (item.score !== undefined && item.score !== null) {
            const scoreBadge = document.createElement('span');
            scoreBadge.className = 'meta-badge score-badge';
            scoreBadge.textContent = `Score: ${item.score}`;
            badgesContainer.appendChild(scoreBadge);
        }
        info.appendChild(badgesContainer);
        
        if (item.tags && item.tags.length > 0) {
            const tagsContainer = document.createElement('div');
            tagsContainer.className = 'card-tags-pills';
            
            const displayTags = item.tags.slice(0, 4);
            displayTags.forEach(tag => {
                const pill = document.createElement('span');
                pill.className = 'tag-pill';
                pill.textContent = tag;
                pill.style.cursor = 'pointer';
                pill.addEventListener('click', (e) => {
                    e.stopPropagation();
                    searchTag(tag);
                });
                tagsContainer.appendChild(pill);
            });
            info.appendChild(tagsContainer);
        }
        
        card.appendChild(info);
        grid.appendChild(card);
    });
    
    container.appendChild(grid);
    initCardTilts();
}

// ===== SUBSCRIPTIONS =====
async function loadSubscriptionsList() {
    const container = document.getElementById('subscriptionsContainer');
    container.innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i><p>Loading subscriptions...</p></div>';
    
    try {
        const res = await fetch('/api/subscriptions');
        const data = await res.json();
        renderSubscriptions(data);
    } catch(e) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-circle-exclamation"></i><p>Failed to load subscriptions</p></div>';
    }
}

function renderSubscriptions(subs) {
    const container = document.getElementById('subscriptionsContainer');
    if (!subs || subs.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-users"></i><p>No active artist subscriptions yet</p></div>';
        return;
    }
    
    let html = '<div class="subscriptions-grid animate">';
    subs.forEach(s => {
        const lastCheckedStr = s.last_checked ? new Date(s.last_checked * 1000).toLocaleString() : 'Never checked';
        const plat = s.platform || 'generic';
        
        html += `
            <div class="card sub-card" data-sub-id="${s.id}">
                <div class="sub-card-header">
                    <div class="sub-card-info">
                        <h3>${esc(s.name)}</h3>
                        <span class="gallery-plat-tag ${platClass(plat)}">${plat}</span>
                    </div>
                    <button class="btn-danger btn-sm delete-sub-btn" onclick="deleteSubscription('${s.id}')" title="Delete Subscription"><i class="fas fa-trash-can"></i></button>
                </div>
                <div class="sub-card-body">
                    <p><i class="fas fa-link"></i> <a href="${s.url}" target="_blank" class="sub-link">${esc(s.url)}</a></p>
                    <p><i class="fas fa-clock"></i> Last Update Check: <span class="sub-meta-val">${lastCheckedStr}</span></p>
                    <p><i class="fas fa-cloud-arrow-down"></i> Total Downloaded: <span class="sub-meta-val">${s.downloaded_count || 0} posts</span></p>
                </div>
                <div class="sub-card-actions">
                    <button class="btn-primary btn-sm" onclick="updateSingleSubscription('${s.id}')"><i class="fas fa-sync"></i> Check Updates</button>
                </div>
            </div>
        `;
    });
    container.innerHTML = html + '</div>';
    
    initCardTilts();
}

async function addSubscription() {
    const name = document.getElementById('subName').value.trim();
    const url = document.getElementById('subUrl').value.trim();
    
    if (!name || !url) return notify('Please enter both name and profile URL', 'error');
    
    const addBtn = document.getElementById('addSubscriptionBtn');
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Subscribing...';
    
    try {
        const res = await fetch('/api/subscriptions/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, url })
        });
        const data = await res.json();
        
        if (data.ok) {
            notify(`Subscribed to artist "${name}"`, 'success');
            document.getElementById('subName').value = '';
            document.getElementById('subUrl').value = '';
            loadSubscriptionsList();
        } else {
            notify(data.error || 'Failed to add subscription', 'error');
        }
    } catch(e) {
        notify('Subscription failed', 'error');
    } finally {
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fas fa-plus"></i> Subscribe';
    }
}

async function deleteSubscription(id) {
    if (!confirm('Are you sure you want to unsubscribe?')) return;
    
    try {
        const res = await fetch('/api/subscriptions/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        
        if (data.ok) {
            notify('Unsubscribed successfully', 'success');
            loadSubscriptionsList();
        } else {
            notify(data.error || 'Failed to delete subscription', 'error');
        }
    } catch(e) {
        notify('Delete operation failed', 'error');
    }
}

async function updateSingleSubscription(id) {
    notify('Checking for updates in background...', 'success');
    
    try {
        const res = await fetch('/api/subscriptions/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.ok) {
            setTimeout(loadSubscriptionsList, 2500);
        }
    } catch(e) {
        notify('Update check failed', 'error');
    }
}

async function updateAllSubscriptions() {
    const btn = document.getElementById('updateAllSubsBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking Updates...';
    notify('Checking updates for all creators...', 'success');
    
    try {
        const res = await fetch('/api/subscriptions/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.ok) {
            setTimeout(() => {
                loadSubscriptionsList();
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-sync"></i> Check for Updates (All)';
            }, 3000);
        }
    } catch(e) {
        notify('Update check failed', 'error');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync"></i> Check for Updates (All)';
    }
}

// ===== AUTOCOMPLETE =====
let activeSuggestionIndex = -1;
let currentSuggestions = [];
let autocompleteTimeout = null;
let autocompleteAbortController = null;

function getActiveToken(inputVal) {
    if (!inputVal) return { token: "", prefix: "" };
    const lastSpaceIdx = inputVal.lastIndexOf(" ");
    if (lastSpaceIdx === -1) {
        return { token: inputVal, prefix: "" };
    } else {
        return { token: inputVal.substring(lastSpaceIdx + 1), prefix: inputVal.substring(0, lastSpaceIdx + 1) };
    }
}

function shouldRequestSuggestions(token) {
    if (!token || token.length < 2) return false;
    if (token.startsWith("-")) return false;
    const metatags = ["rating:", "order:", "score:", "id:", "date:", "user:", "pool:", "fav:", "source:", "parent:"];
    if (metatags.some(m => token.toLowerCase().startsWith(m))) return false;
    if (!/^[a-zA-Z0-9_\-:\(\)]+$/.test(token)) return false;
    return true;
}

function formatPostCount(count) {
    if (count >= 1000000) {
        return (count / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
    }
    if (count >= 1000) {
        return (count / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
    }
    return count.toString();
}

function renderHighlightedLabel(parentElement, labelText, searchToken) {
    parentElement.textContent = '';
    if (!searchToken) {
        parentElement.appendChild(document.createTextNode(labelText));
        return;
    }
    const lowerLabel = labelText.toLowerCase();
    const lowerSearch = searchToken.toLowerCase();
    let index = lowerLabel.indexOf(lowerSearch);
    
    if (index === -1) {
        parentElement.appendChild(document.createTextNode(labelText));
        return;
    }
    
    let lastIndex = 0;
    while (index !== -1) {
        if (index > lastIndex) {
            parentElement.appendChild(document.createTextNode(labelText.substring(lastIndex, index)));
        }
        const span = document.createElement('span');
        span.className = 'autocomplete-highlight';
        span.textContent = labelText.substring(index, index + searchToken.length);
        parentElement.appendChild(span);
        
        lastIndex = index + searchToken.length;
        index = lowerLabel.indexOf(lowerSearch, lastIndex);
    }
    
    if (lastIndex < labelText.length) {
        parentElement.appendChild(document.createTextNode(labelText.substring(lastIndex)));
    }
}

function selectSuggestion(item) {
    const input = document.getElementById('discoverSearchInput');
    if (!input) return;
    const currentVal = input.value;
    const { prefix } = getActiveToken(currentVal);
    input.value = prefix + item.tag + ' ';
    closeAutocompleteDropdown();
    input.focus();
}

function closeAutocompleteDropdown() {
    const dropdown = document.getElementById('discoverAutocompleteDropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
        dropdown.textContent = '';
    }
    const input = document.getElementById('discoverSearchInput');
    if (input) {
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
    }
    activeSuggestionIndex = -1;
    currentSuggestions = [];
}

async function fetchSuggestions(fullInput) {
    const { token } = getActiveToken(fullInput);
    if (!shouldRequestSuggestions(token)) {
        closeAutocompleteDropdown();
        return;
    }
    
    if (autocompleteAbortController) {
        autocompleteAbortController.abort();
    }
    
    autocompleteAbortController = new AbortController();
    const signal = autocompleteAbortController.signal;
    
    const dropdown = document.getElementById('discoverAutocompleteDropdown');
    if (!dropdown) return;
    
    dropdown.textContent = '';
    const loadingRow = document.createElement('div');
    loadingRow.className = 'autocomplete-loading';
    const spinner = document.createElement('i');
    spinner.className = 'fas fa-spinner fa-spin';
    loadingRow.appendChild(spinner);
    loadingRow.appendChild(document.createTextNode(' Fetching suggestions...'));
    dropdown.appendChild(loadingRow);
    dropdown.style.display = 'block';
    
    const input = document.getElementById('discoverSearchInput');
    if (input) {
        input.setAttribute('aria-expanded', 'true');
    }
    
    const sources = [];
    if (document.getElementById('cb-danbooru')?.checked) sources.push('danbooru');
    if (document.getElementById('cb-gelbooru')?.checked) sources.push('gelbooru');
    
    if (sources.length === 0) {
        closeAutocompleteDropdown();
        return;
    }
    
    const url = `/api/discover/tag-suggestions?q=${encodeURIComponent(fullInput)}&sources=${encodeURIComponent(sources.join(','))}`;
    
    try {
        const response = await fetch(url, { signal });
        if (!response.ok) {
            throw new Error(`API returned HTTP ${response.status}`);
        }
        const data = await response.json();
        
        if (signal.aborted) return;
        
        const suggestions = data.suggestions || [];
        if (suggestions.length === 0) {
            closeAutocompleteDropdown();
            return;
        }
        
        currentSuggestions = suggestions;
        activeSuggestionIndex = -1;
        
        dropdown.textContent = '';
        
        for (let i = 0; i < suggestions.length; i++) {
            const item = suggestions[i];
            const row = document.createElement('div');
            row.className = 'autocomplete-row';
            row.setAttribute('role', 'option');
            row.setAttribute('id', `autocomplete-opt-${i}`);
            row.setAttribute('aria-selected', 'false');
            
            const infoDiv = document.createElement('div');
            infoDiv.className = 'autocomplete-tag-info';
            
            const labelSpan = document.createElement('span');
            labelSpan.className = 'autocomplete-tag-label';
            renderHighlightedLabel(labelSpan, item.label, token);
            infoDiv.appendChild(labelSpan);
            
            if (item.label !== item.tag) {
                const syntaxSpan = document.createElement('span');
                syntaxSpan.className = 'autocomplete-tag-syntax';
                syntaxSpan.textContent = item.tag;
                infoDiv.appendChild(syntaxSpan);
            }
            row.appendChild(infoDiv);
            
            const metaDiv = document.createElement('div');
            metaDiv.className = 'autocomplete-tag-meta';
            
            if (item.category) {
                const catBadge = document.createElement('span');
                const catClass = `category-${item.category.toLowerCase()}`;
                catBadge.className = `autocomplete-category-badge ${catClass}`;
                catBadge.textContent = item.category;
                metaDiv.appendChild(catBadge);
            }
            
            const postCountSpan = document.createElement('span');
            postCountSpan.className = 'autocomplete-post-count';
            postCountSpan.textContent = formatPostCount(item.post_count);
            metaDiv.appendChild(postCountSpan);
            
            const sourceSpan = document.createElement('span');
            sourceSpan.className = 'autocomplete-source-badge';
            let sourceText = '';
            const hasDan = item.sources.includes('danbooru');
            const hasGel = item.sources.includes('gelbooru');
            if (hasDan && hasGel) {
                sourceText = 'D + G';
            } else if (hasDan) {
                sourceText = 'D';
            } else if (hasGel) {
                sourceText = 'G';
            }
            sourceSpan.textContent = sourceText;
            metaDiv.appendChild(sourceSpan);
            
            row.appendChild(metaDiv);
            
            row.addEventListener('click', function(e) {
                e.stopPropagation();
                selectSuggestion(item);
            });
            
            dropdown.appendChild(row);
        }
        
        dropdown.style.display = 'block';
        if (input) {
            input.setAttribute('aria-expanded', 'true');
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            return;
        }
        console.error('Error fetching autocomplete suggestions:', err);
        closeAutocompleteDropdown();
    }
}

function handleAutocompleteKeydown(e) {
    const dropdown = document.getElementById('discoverAutocompleteDropdown');
    const isOpen = dropdown && dropdown.style.display !== 'none';
    
    if (!isOpen) {
        if (e.key === 'Enter') {
            handleDiscoverSearch();
        }
        return;
    }
    
    const rows = dropdown.querySelectorAll('.autocomplete-row');
    
    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            if (rows.length === 0) return;
            
            if (activeSuggestionIndex >= 0 && activeSuggestionIndex < rows.length) {
                rows[activeSuggestionIndex].classList.remove('active');
                rows[activeSuggestionIndex].setAttribute('aria-selected', 'false');
            }
            
            activeSuggestionIndex++;
            if (activeSuggestionIndex >= rows.length) {
                activeSuggestionIndex = 0;
            }
            
            rows[activeSuggestionIndex].classList.add('active');
            rows[activeSuggestionIndex].setAttribute('aria-selected', 'true');
            rows[activeSuggestionIndex].scrollIntoView({ block: 'nearest' });
            
            const input = document.getElementById('discoverSearchInput');
            if (input) {
                input.setAttribute('aria-activedescendant', rows[activeSuggestionIndex].id);
            }
            break;
            
        case 'ArrowUp':
            e.preventDefault();
            if (rows.length === 0) return;
            
            if (activeSuggestionIndex >= 0 && activeSuggestionIndex < rows.length) {
                rows[activeSuggestionIndex].classList.remove('active');
                rows[activeSuggestionIndex].setAttribute('aria-selected', 'false');
            }
            
            activeSuggestionIndex--;
            if (activeSuggestionIndex < 0) {
                activeSuggestionIndex = rows.length - 1;
            }
            
            rows[activeSuggestionIndex].classList.add('active');
            rows[activeSuggestionIndex].setAttribute('aria-selected', 'true');
            rows[activeSuggestionIndex].scrollIntoView({ block: 'nearest' });
            
            const input2 = document.getElementById('discoverSearchInput');
            if (input2) {
                input2.setAttribute('aria-activedescendant', rows[activeSuggestionIndex].id);
            }
            break;
            
        case 'Enter':
            if (activeSuggestionIndex >= 0 && activeSuggestionIndex < currentSuggestions.length) {
                e.preventDefault();
                selectSuggestion(currentSuggestions[activeSuggestionIndex]);
            } else {
                closeAutocompleteDropdown();
                handleDiscoverSearch();
            }
            break;
            
        case 'Tab':
            if (activeSuggestionIndex >= 0 && activeSuggestionIndex < currentSuggestions.length) {
                e.preventDefault();
                selectSuggestion(currentSuggestions[activeSuggestionIndex]);
            }
            break;
            
        case 'Escape':
            e.preventDefault();
            closeAutocompleteDropdown();
            break;
    }
}

function setupAutocomplete() {
    const input = document.getElementById('discoverSearchInput');
    if (!input) return;
    
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', 'discoverAutocompleteDropdown');
    
    input.addEventListener('input', function(e) {
        const val = this.value;
        const { token } = getActiveToken(val);
        
        if (autocompleteTimeout) {
            clearTimeout(autocompleteTimeout);
        }
        
        if (!shouldRequestSuggestions(token)) {
            closeAutocompleteDropdown();
            return;
        }
        
        autocompleteTimeout = setTimeout(() => {
            fetchSuggestions(val);
        }, 250);
    });
    
    input.addEventListener('keydown', handleAutocompleteKeydown);
    
    // Close when clicking outside
    document.addEventListener('click', function(e) {
        const wrapper = document.querySelector('.autocomplete-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            closeAutocompleteDropdown();
        }
    });
    
    // Close when source selection changes, then fetch fresh suggestions if input still qualifies
    const cbDanbooru = document.getElementById('cb-danbooru');
    const cbGelbooru = document.getElementById('cb-gelbooru');
    
    const handleSourceChange = () => {
        closeAutocompleteDropdown();
        const currentVal = input.value;
        const { token } = getActiveToken(currentVal);
        if (shouldRequestSuggestions(token)) {
            fetchSuggestions(currentVal);
        }
    };
    
    if (cbDanbooru) cbDanbooru.addEventListener('change', handleSourceChange);
    if (cbGelbooru) cbGelbooru.addEventListener('change', handleSourceChange);
}

// ===== VIEWER MODAL =====
let currentViewerIndex = -1;
let previouslyFocusedElement = null;
let viewerTouchStartX = 0;
let viewerTouchStartY = 0;

function searchTag(tag) {
    const input = document.getElementById('discoverSearchInput');
    if (input) {
        input.value = tag;
    }
    closeViewerModal();
    handleDiscoverSearch();
}

function getExtension(url) {
    if (!url) return 'image';
    try {
        const pathname = new URL(url).pathname;
        const lastDot = pathname.lastIndexOf('.');
        if (lastDot !== -1) {
            const ext = pathname.substring(lastDot + 1).toLowerCase();
            const cleanExt = ext.split(/[?#]/)[0];
            if (cleanExt && cleanExt.length <= 4) {
                return cleanExt;
            }
        }
    } catch (e) {
        const parts = url.split(/[?#]/)[0].split('.');
        if (parts.length > 1) {
            const ext = parts[parts.length - 1].toLowerCase();
            if (ext.length <= 4) return ext;
        }
    }
    return 'image';
}

function copyPostLink(url) {
    if (!navigator.clipboard) {
        const textArea = document.createElement("textarea");
        textArea.value = url;
        textArea.style.position = "fixed";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
            showCopyConfirmation();
        } catch (err) {
            console.error('Fallback copy link failed:', err);
            notify('Failed to copy post link', 'error');
        }
        document.body.removeChild(textArea);
        return;
    }
    
    navigator.clipboard.writeText(url).then(() => {
        showCopyConfirmation();
    }).catch(err => {
        console.error('Copy link failed:', err);
        notify('Failed to copy post link', 'error');
    });
}

function showCopyConfirmation() {
    notify('Post link copied', 'success');
    const liveRegion = document.getElementById('viewerLiveRegion');
    if (liveRegion) {
        liveRegion.textContent = 'Post link copied to clipboard';
    }
}

function loadViewerImage(displayUrl, thumbnailUrl, source) {
    const img = document.getElementById('viewerImage');
    const spinner = document.getElementById('viewerImageSpinner');
    const errorDiv = document.getElementById('viewerImageError');
    const liveRegion = document.getElementById('viewerLiveRegion');
    
    if (!img || !spinner || !errorDiv) return;
    
    img.style.display = 'none';
    errorDiv.style.display = 'none';
    spinner.style.display = 'block';
    
    function getRenderUrl(rawUrl) {
        if (!rawUrl) return '';
        if (source === 'gelbooru') {
            return `/api/proxy-image?url=${encodeURIComponent(rawUrl)}`;
        }
        return rawUrl;
    }
    
    const displayRenderUrl = getRenderUrl(displayUrl);
    const thumbnailRenderUrl = getRenderUrl(thumbnailUrl);
    
    if (!displayRenderUrl) {
        if (thumbnailRenderUrl) {
            tryThumbnailFallback(thumbnailRenderUrl);
        } else {
            showImageError();
        }
        return;
    }
    
    const displayImg = new Image();
    displayImg.onload = function() {
        img.src = displayRenderUrl;
        spinner.style.display = 'none';
        img.style.display = 'block';
    };
    
    displayImg.onerror = function() {
        console.warn('Viewer display_url failed to load, trying thumbnail fallback:', displayUrl);
        if (thumbnailRenderUrl) {
            tryThumbnailFallback(thumbnailRenderUrl);
        } else {
            showImageError();
        }
    };
    
    displayImg.src = displayRenderUrl;
    
    function tryThumbnailFallback(thumbUrl) {
        const thumbImg = new Image();
        thumbImg.onload = function() {
            img.src = thumbUrl;
            spinner.style.display = 'none';
            img.style.display = 'block';
            if (liveRegion) {
                liveRegion.textContent = 'Display image failed to load. Showing thumbnail preview instead.';
            }
        };
        thumbImg.onerror = function() {
            showImageError();
        };
        thumbImg.src = thumbUrl;
    }
    
    function showImageError() {
        spinner.style.display = 'none';
        img.style.display = 'none';
        errorDiv.style.display = 'flex';
        if (liveRegion) {
            liveRegion.textContent = 'Failed to load image illustration.';
        }
    }
}

function renderViewerTagsGroup(elementId, groupWrapperId, tags) {
    const container = document.getElementById(elementId);
    const wrapper = document.getElementById(groupWrapperId);
    if (!container || !wrapper) return;
    
    container.textContent = '';
    
    if (!tags || tags.length === 0) {
        wrapper.style.display = 'none';
        return;
    }
    
    wrapper.style.display = 'block';
    
    tags.forEach(tag => {
        const pill = document.createElement('span');
        pill.className = 'tag-pill';
        pill.textContent = tag;
        pill.style.cursor = 'pointer';
        pill.addEventListener('click', () => {
            searchTag(tag);
        });
        container.appendChild(pill);
    });
}

function openViewerModal(index) {
    if (index < 0 || index >= discoverResults.length) return;
    
    previouslyFocusedElement = document.activeElement;
    currentViewerIndex = index;
    renderViewerPost();
    
    const modal = document.getElementById('discoverViewerModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.focus();
    }
    
    document.body.classList.add('modal-open');
    preloadAdjacentImages();
}

function closeViewerModal() {
    const modal = document.getElementById('discoverViewerModal');
    if (modal) {
        modal.style.display = 'none';
    }
    document.body.classList.remove('modal-open');
    
    if (previouslyFocusedElement && typeof previouslyFocusedElement.focus === 'function') {
        previouslyFocusedElement.focus();
    }
    
    currentViewerIndex = -1;
}

function renderViewerPost() {
    if (currentViewerIndex < 0 || currentViewerIndex >= discoverResults.length) return;
    
    const post = discoverResults[currentViewerIndex];
    
    const counter = document.getElementById('viewerCounter');
    if (counter) {
        counter.textContent = `${currentViewerIndex + 1} / ${discoverResults.length}`;
    }
    
    const title = document.getElementById('viewerTitle');
    if (title) {
        title.textContent = post.title || `${post.source_label} Post ${post.post_id}`;
    }
    
    const srcBadge = document.getElementById('viewerSourceBadge');
    if (srcBadge) {
        srcBadge.textContent = post.source_label;
        srcBadge.className = `gallery-plat-tag ${platClass(post.source)}`;
    }
    
    const ratingBadge = document.getElementById('viewerRatingBadge');
    if (ratingBadge) {
        ratingBadge.textContent = post.rating ? post.rating.charAt(0).toUpperCase() + post.rating.slice(1) : 'Safe';
        ratingBadge.className = `meta-badge rating-${post.rating || 'safe'}`;
    }
    
    const dimsBadge = document.getElementById('viewerDimsBadge');
    if (dimsBadge) {
        if (post.width && post.height) {
            dimsBadge.textContent = `${post.width} x ${post.height}`;
            dimsBadge.style.display = 'inline-block';
        } else {
            dimsBadge.style.display = 'none';
        }
    }
    
    const scoreBadge = document.getElementById('viewerScoreBadge');
    if (scoreBadge) {
        if (post.score !== undefined && post.score !== null) {
            scoreBadge.textContent = `Score: ${post.score}`;
            scoreBadge.style.display = 'inline-block';
        } else {
            scoreBadge.style.display = 'none';
        }
    }
    
    loadViewerImage(post.display_url, post.thumbnail_url, post.source);
    
    const downloadBtn = document.getElementById('viewerDownloadBtn');
    if (downloadBtn) {
        if (post.original_url) {
            downloadBtn.href = post.original_url;
            downloadBtn.target = '_blank';
            const ext = getExtension(post.original_url);
            const filename = `${post.source}_${post.post_id}.${ext}`;
            downloadBtn.setAttribute('download', filename);
            downloadBtn.removeAttribute('title');
            downloadBtn.classList.remove('disabled');
            downloadBtn.style.pointerEvents = 'auto';
        } else {
            downloadBtn.removeAttribute('href');
            downloadBtn.removeAttribute('download');
            downloadBtn.setAttribute('title', 'Original image URL is not available for this post.');
            downloadBtn.classList.add('disabled');
            downloadBtn.style.pointerEvents = 'none';
        }
    }
    
    const postUrlBtn = document.getElementById('viewerPostUrlBtn');
    if (postUrlBtn) {
        postUrlBtn.href = post.post_url;
        postUrlBtn.textContent = `View on ${post.source_label}`;
    }
    
    const copyLinkBtn = document.getElementById('viewerCopyLinkBtn');
    if (copyLinkBtn) {
        const newCopyBtn = copyLinkBtn.cloneNode(true);
        copyLinkBtn.parentNode.replaceChild(newCopyBtn, copyLinkBtn);
        newCopyBtn.addEventListener('click', () => {
            copyPostLink(post.post_url);
        });
    }
    
    const openTabBtn = document.getElementById('viewerOpenTabBtn');
    if (openTabBtn) {
        const renderUrl = post.source === 'gelbooru'
            ? `/api/proxy-image?url=${encodeURIComponent(post.display_url || post.thumbnail_url)}`
            : (post.display_url || post.thumbnail_url);
        openTabBtn.href = renderUrl;
    }
    
    renderViewerTagsGroup('viewerArtistTags', 'viewerArtistTagsGroup', post.artist_tags);
    renderViewerTagsGroup('viewerCharacterTags', 'viewerCharacterTagsGroup', post.character_tags);
    renderViewerTagsGroup('viewerCopyrightTags', 'viewerCopyrightTagsGroup', post.copyright_tags);
    renderViewerTagsGroup('viewerGeneralTags', 'viewerGeneralTagsGroup', post.tags);
}

function navigateViewer(direction) {
    if (discoverResults.length === 0) return;
    
    let newIndex = currentViewerIndex + direction;
    if (newIndex < 0) {
        newIndex = discoverResults.length - 1;
    } else if (newIndex >= discoverResults.length) {
        newIndex = 0;
    }
    
    currentViewerIndex = newIndex;
    renderViewerPost();
    preloadAdjacentImages();
}

function preloadAdjacentImages() {
    if (discoverResults.length <= 1) return;
    
    const prevIdx = (currentViewerIndex - 1 + discoverResults.length) % discoverResults.length;
    const nextIdx = (currentViewerIndex + 1) % discoverResults.length;
    
    const prevPost = discoverResults[prevIdx];
    const nextPost = discoverResults[nextIdx];
    
    if (prevPost) {
        const prevUrl = prevPost.source === 'gelbooru'
            ? `/api/proxy-image?url=${encodeURIComponent(prevPost.display_url)}`
            : prevPost.display_url;
        const imgPrev = new Image();
        imgPrev.src = prevUrl;
    }
    
    if (nextPost) {
        const nextUrl = nextPost.source === 'gelbooru'
            ? `/api/proxy-image?url=${encodeURIComponent(nextPost.display_url)}`
            : nextPost.display_url;
        const imgNext = new Image();
        imgNext.src = nextUrl;
    }
}

function trapFocus(e) {
    if (e.key !== 'Tab') return;
    
    const modal = document.getElementById('discoverViewerModal');
    if (!modal || modal.style.display === 'none') return;
    
    const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const focusables = Array.from(modal.querySelectorAll(focusableSelectors))
                            .filter(el => !el.disabled && el.style.display !== 'none' && el.getAttribute('tabindex') !== '-1');
                            
    if (focusables.length === 0) {
        e.preventDefault();
        return;
    }
    
    const firstFocusable = focusables[0];
    const lastFocusable = focusables[focusables.length - 1];
    
    if (e.shiftKey) {
        if (document.activeElement === firstFocusable) {
            lastFocusable.focus();
            e.preventDefault();
        }
    } else {
        if (document.activeElement === lastFocusable) {
            firstFocusable.focus();
            e.preventDefault();
        }
    }
}

function handleViewerKeydown(e) {
    const modal = document.getElementById('discoverViewerModal');
    if (!modal || modal.style.display === 'none') return;
    
    if (e.key === 'Escape') {
        closeViewerModal();
        e.preventDefault();
        return;
    }
    
    if (e.key === 'ArrowLeft') {
        navigateViewer(-1);
        e.preventDefault();
        return;
    }
    
    if (e.key === 'ArrowRight') {
        navigateViewer(1);
        e.preventDefault();
        return;
    }
    
    trapFocus(e);
}

function handleTouchStart(e) {
    viewerTouchStartX = e.changedTouches[0].screenX;
    viewerTouchStartY = e.changedTouches[0].screenY;
}

function handleTouchEnd(e) {
    const touchEndX = e.changedTouches[0].screenX;
    const touchEndY = e.changedTouches[0].screenY;
    
    const diffX = touchEndX - viewerTouchStartX;
    const diffY = touchEndY - viewerTouchStartY;
    
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 60) {
        if (diffX > 0) {
            navigateViewer(-1);
        } else {
            navigateViewer(1);
        }
    }
}

function setupViewer() {
    window.addEventListener('keydown', handleViewerKeydown);
    
    const closeBtn = document.getElementById('viewerCloseBtn');
    if (closeBtn) closeBtn.addEventListener('click', closeViewerModal);
    
    const modal = document.getElementById('discoverViewerModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeViewerModal();
            }
        });
    }
    
    const prevBtn = document.getElementById('viewerPrevBtn');
    if (prevBtn) prevBtn.addEventListener('click', () => navigateViewer(-1));
    
    const nextBtn = document.getElementById('viewerNextBtn');
    if (nextBtn) nextBtn.addEventListener('click', () => navigateViewer(1));
    
    const imgContainer = document.querySelector('.viewer-image-container');
    if (imgContainer) {
        imgContainer.addEventListener('touchstart', handleTouchStart, { passive: true });
        imgContainer.addEventListener('touchend', handleTouchEnd, { passive: true });
    }
}

// ===== UTILS =====
function esc(s) { return s ? s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) : ''; }

function notify(msg, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let iconClass = 'fa-solid fa-circle-info';
    if (type === 'success') iconClass = 'fa-solid fa-circle-check';
    else if (type === 'error') iconClass = 'fa-solid fa-circle-xmark';
    else if (type === 'warning') iconClass = 'fa-solid fa-triangle-exclamation';
    
    toast.innerHTML = `
        <i class="${iconClass}"></i>
        <span class="toast-message">${msg}</span>
        <button class="toast-close" onclick="this.parentElement.classList.add('toast-out'); setTimeout(() => this.parentElement.remove(), 300)">✕</button>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('toast-out');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}
