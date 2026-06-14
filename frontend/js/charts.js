/**
 * Chart.js utilities for data visualization
 */

/**
 * Create language distribution pie chart
 * @param {string} canvasId - Canvas element ID
 * @param {object} languageData - Language statistics from GitHub
 */
function createLanguageChart(canvasId, languageData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Prepare data
    const labels = Object.keys(languageData);
    const data = Object.values(languageData);
    const total = data.reduce((sum, val) => sum + val, 0);

    // Calculate percentages
    const percentages = data.map(val => ((val / total) * 100).toFixed(1));

    // Color palette
    const colors = [
        '#6366f1', // Primary
        '#8b5cf6', // Purple
        '#ec4899', // Pink
        '#10b981', // Green
        '#f59e0b', // Orange
        '#ef4444', // Red
        '#3b82f6', // Blue
        '#14b8a6', // Teal
    ];

    // Destroy existing chart if any
    if (window.languageChartInstance) {
        window.languageChartInstance.destroy();
    }

    // Create chart
    window.languageChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        font: {
                            size: 12,
                            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto'
                        },
                        generateLabels: function (chart) {
                            const data = chart.data;
                            if (data.labels.length && data.datasets.length) {
                                return data.labels.map((label, i) => {
                                    const value = data.datasets[0].data[i];
                                    const percentage = percentages[i];
                                    return {
                                        text: `${label} (${percentage}%)`,
                                        fillStyle: data.datasets[0].backgroundColor[i],
                                        hidden: false,
                                        index: i
                                    };
                                });
                            }
                            return [];
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const label = context.label || '';
                            const value = context.parsed;
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${formatNumber(value)} bytes (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Get language color for badges
 * @param {string} language - Programming language name
 * @returns {string} - Color hex code
 */
function getLanguageColor(language) {
    const colors = {
        'JavaScript': '#f1e05a',
        'TypeScript': '#2b7489',
        'Python': '#3572A5',
        'Java': '#b07219',
        'C++': '#f34b7d',
        'C': '#555555',
        'C#': '#178600',
        'PHP': '#4F5D95',
        'Ruby': '#701516',
        'Go': '#00ADD8',
        'Rust': '#dea584',
        'Swift': '#ffac45',
        'Kotlin': '#F18E33',
        'HTML': '#e34c26',
        'CSS': '#563d7c',
        'Shell': '#89e051',
        'Vue': '#41b883',
        'Dart': '#00B4AB',
    };
    return colors[language] || '#858585';
}

/**
 * Format large numbers with K, M suffixes
 * @param {number} num - Number to format
 * @returns {string} - Formatted number
 */
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        createLanguageChart,
        getLanguageColor,
        formatNumber,
    };
}
