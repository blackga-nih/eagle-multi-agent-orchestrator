/**
 * admin-panels.js - Admin Cost Report & Subscription/Usage Panels
 *
 * Handles all admin cost report panels and subscription/usage information
 * panels. Each function fetches data from the API and renders the results
 * into the #usageInfo panel using safe DOM APIs (createElement,
 * createTextNode - never innerHTML).
 *
 * Uses the window.AdminPanels namespace pattern (not ES modules) to stay
 * consistent with the rest of the frontend architecture.
 *
 * Prerequisites:
 *   - window.ApiClient  (API fetch wrappers with Bearer token auth)
 *   - window.Auth       (getCurrentUser returns {email, tenant_id, ...})
 *   - window.UI         (createInfoPanel, createBadge, createStatItem, createStyledDiv)
 *
 * Usage:
 *   AdminPanels.checkAdminAccess(userInfoDiv);
 *   AdminPanels.showUsage(tenantId);
 *   AdminPanels.showSessions(tenantId);
 *   AdminPanels.showSubscription(tenantId);
 *   AdminPanels.showAdminOverallCost(tenantId);
 *   AdminPanels.showAdminPerUserCost(tenantId);
 *   AdminPanels.showAdminServiceCost(tenantId);
 *   AdminPanels.showComprehensiveReport(tenantId);
 */
window.AdminPanels = (function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    /**
     * Render an error state into the #usageInfo panel.
     *
     * Creates a div with the 'error' class and the given message text,
     * then appends it to the panel after clearing its contents.
     *
     * @param {string} message - The error message to display.
     */
    function renderError(message) {
        var panel = document.getElementById('usageInfo');
        if (!panel) {
            return;
        }
        panel.textContent = '';
        panel.style.display = 'block';

        var errorDiv = document.createElement('div');
        errorDiv.className = 'error';
        errorDiv.textContent = message;
        panel.appendChild(errorDiv);
    }

    /**
     * Prompt the user for a number of days, defaulting to 30.
     *
     * Displays a browser prompt dialog. If the user cancels, returns null
     * so the caller can abort the operation. Otherwise parses the input
     * as an integer and falls back to 30 if the result is NaN.
     *
     * @param {string} label - Description shown in the prompt dialog.
     * @returns {number|null} The number of days, or null if cancelled.
     */
    function promptDays(label) {
        var input = prompt(label, '30');
        if (input === null) {
            return null;
        }
        var parsed = parseInt(input, 10);
        return isNaN(parsed) ? 30 : parsed;
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Check whether the current user has admin privileges.
     *
     * Calls ApiClient.getAdminTenants(). On success, shows the
     * #adminControls element (display: block) and appends an admin role
     * badge plus a tenant access information paragraph to the supplied
     * userInfoDiv. On error (user is not admin), the admin controls
     * remain hidden and no UI changes are made.
     *
     * @param {HTMLElement} userInfoDiv - The container element to append
     *   admin role information into (typically #userInfo).
     * @returns {Promise<void>}
     */
    async function checkAdminAccess(userInfoDiv) {
        try {
            var adminData = await window.ApiClient.getAdminTenants();

            // Show the admin controls section
            var adminControls = document.getElementById('adminControls');
            if (adminControls) {
                adminControls.style.display = 'block';
            }

            // Append role badge to userInfoDiv
            var roleP = document.createElement('p');
            var roleStrong = document.createElement('strong');
            roleStrong.textContent = 'Role:';
            roleP.appendChild(roleStrong);
            roleP.appendChild(document.createTextNode(' '));

            var adminBadge = window.UI.createBadge('Admin', 'badge-admin');
            roleP.appendChild(adminBadge);

            // Append tenant access info
            var accessP = document.createElement('p');
            accessP.style.fontSize = '12px';
            accessP.style.opacity = '0.8';
            accessP.textContent = 'Admin access for: ' + adminData.admin_tenants.join(', ');

            userInfoDiv.appendChild(roleP);
            userInfoDiv.appendChild(accessP);
        } catch (error) {
            // User is not admin - keep admin controls hidden, no UI changes
        }
    }

    /**
     * Display usage statistics for a tenant.
     *
     * Calls ApiClient.getUsage(tenantId) and renders the results into
     * the #usageInfo panel with a title, Organization / Total Messages /
     * Active Sessions stat items, and a pre block containing the raw
     * metrics JSON.
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showUsage(tenantId) {
        try {
            var usage = await window.ApiClient.getUsage(tenantId);

            window.UI.createInfoPanel('Usage Statistics', function (panel) {
                panel.appendChild(
                    window.UI.createStatItem('Organization', usage.tenant_id)
                );
                panel.appendChild(
                    window.UI.createStatItem('Total Messages', String(usage.total_messages))
                );
                panel.appendChild(
                    window.UI.createStatItem('Active Sessions', String(usage.sessions))
                );

                var pre = document.createElement('pre');
                pre.style.cssText = 'background: var(--nci-bg); padding: 15px; border-radius: 8px; overflow-x: auto;';
                pre.textContent = JSON.stringify(usage.metrics, null, 2);
                panel.appendChild(pre);
            });
        } catch (error) {
            renderError('Failed to load usage statistics');
        }
    }

    /**
     * Display active sessions for a tenant.
     *
     * Calls ApiClient.getSessions(tenantId) and renders the results into
     * the #usageInfo panel with a title, Organization name, and a pre
     * block containing the sessions JSON.
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showSessions(tenantId) {
        try {
            var sessions = await window.ApiClient.getSessions(tenantId);

            window.UI.createInfoPanel('Active Sessions', function (panel) {
                panel.appendChild(
                    window.UI.createStatItem('Organization', sessions.tenant_id)
                );

                var pre = document.createElement('pre');
                pre.style.cssText = 'background: var(--nci-bg); padding: 15px; border-radius: 8px; overflow-x: auto;';
                pre.textContent = JSON.stringify(sessions.sessions, null, 2);
                panel.appendChild(pre);
            });
        } catch (error) {
            renderError('Failed to load sessions');
        }
    }

    /**
     * Display subscription details for a tenant.
     *
     * Calls ApiClient.getSubscription(tenantId) and renders:
     *   - Title "Subscription Details"
     *   - Tier badge (badge-premium, badge-advanced, or badge-basic)
     *   - Plan Limits section (daily_messages, monthly_messages,
     *     max_session_duration, concurrent_sessions, mcp_server_access
     *     shown as Enabled/Disabled with colored text)
     *   - Current Usage section (daily/monthly percentages, active
     *     sessions count)
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showSubscription(tenantId) {
        try {
            var info = await window.ApiClient.getSubscription(tenantId);

            var tierBadgeClass = info.subscription_tier === 'premium' ? 'badge-premium' :
                                 info.subscription_tier === 'advanced' ? 'badge-advanced' : 'badge-basic';

            window.UI.createInfoPanel('Subscription Details', function (panel) {
                // Tier badge
                var tierP = document.createElement('p');
                var tierStrong = document.createElement('strong');
                tierStrong.textContent = 'Tier:';
                tierP.appendChild(tierStrong);
                tierP.appendChild(document.createTextNode(' '));
                tierP.appendChild(window.UI.createBadge(info.subscription_tier, tierBadgeClass));
                panel.appendChild(tierP);

                // Plan Limits section
                var limitsDiv = window.UI.createStyledDiv(
                    'background: var(--nci-bg); padding: 20px; border-radius: 8px; margin: 15px 0;'
                );

                var limitsH4 = document.createElement('h4');
                limitsH4.style.cssText = 'margin-bottom: 15px; color: var(--nci-primary);';
                limitsH4.textContent = 'Plan Limits';
                limitsDiv.appendChild(limitsH4);

                var dailyP = document.createElement('p');
                dailyP.textContent = 'Daily Messages: ' + info.limits.daily_messages;
                limitsDiv.appendChild(dailyP);

                var monthlyP = document.createElement('p');
                monthlyP.textContent = 'Monthly Messages: ' + info.limits.monthly_messages;
                limitsDiv.appendChild(monthlyP);

                var durationP = document.createElement('p');
                durationP.textContent = 'Session Duration: ' + info.limits.max_session_duration + ' minutes';
                limitsDiv.appendChild(durationP);

                var concurrentP = document.createElement('p');
                concurrentP.textContent = 'Concurrent Sessions: ' + info.limits.concurrent_sessions;
                limitsDiv.appendChild(concurrentP);

                var mcpP = document.createElement('p');
                mcpP.textContent = 'MCP Access: ';
                var mcpStatus = document.createElement('strong');
                mcpStatus.style.color = info.limits.mcp_server_access ? 'var(--nci-success)' : 'var(--nci-danger)';
                mcpStatus.textContent = info.limits.mcp_server_access ? 'Enabled' : 'Disabled';
                mcpP.appendChild(mcpStatus);
                limitsDiv.appendChild(mcpP);

                panel.appendChild(limitsDiv);

                // Current Usage section
                var usageDiv = window.UI.createStyledDiv(
                    'background: #E9F7EF; padding: 20px; border-radius: 8px;'
                );

                var usageH4 = document.createElement('h4');
                usageH4.style.cssText = 'margin-bottom: 15px; color: var(--nci-primary);';
                usageH4.textContent = 'Current Usage';
                usageDiv.appendChild(usageH4);

                var dailyPct = ((info.current_usage.daily_usage / info.limits.daily_messages) * 100).toFixed(1);
                var dailyUsageP = document.createElement('p');
                dailyUsageP.textContent = 'Daily: ' + info.current_usage.daily_usage + '/' +
                    info.limits.daily_messages + ' (' + dailyPct + '%)';
                usageDiv.appendChild(dailyUsageP);

                var monthlyPct = ((info.current_usage.monthly_usage / info.limits.monthly_messages) * 100).toFixed(1);
                var monthlyUsageP = document.createElement('p');
                monthlyUsageP.textContent = 'Monthly: ' + info.current_usage.monthly_usage + '/' +
                    info.limits.monthly_messages + ' (' + monthlyPct + '%)';
                usageDiv.appendChild(monthlyUsageP);

                var activeSessionsP = document.createElement('p');
                activeSessionsP.textContent = 'Active Sessions: ' + info.current_usage.active_sessions + '/' +
                    info.limits.concurrent_sessions;
                usageDiv.appendChild(activeSessionsP);

                panel.appendChild(usageDiv);
            });
        } catch (error) {
            renderError('Failed to load subscription details');
        }
    }

    /**
     * Display the overall tenant cost report (admin only).
     *
     * Prompts for number of days (default 30). Calls
     * ApiClient.getAdminOverallCost(tenantId, days) and renders:
     *   - Title with days count
     *   - Total cost in a red-bordered div
     *   - Service breakdown entries with percentage badges
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showAdminOverallCost(tenantId) {
        var days = promptDays('Enter days for admin overall cost report (default: 30):');
        if (days === null) {
            return;
        }

        try {
            var data = await window.ApiClient.getAdminOverallCost(tenantId, days);

            window.UI.createInfoPanel('ADMIN: Overall Tenant Cost (' + days + ' days)', function (panel) {
                var costDiv = window.UI.createStyledDiv(
                    'background: #FDECEA; padding: 20px; border-radius: 8px; border: 2px solid var(--nci-danger);'
                );

                var totalH4 = document.createElement('h4');
                totalH4.style.cssText = 'color: var(--nci-primary); margin-bottom: 15px;';
                totalH4.textContent = 'Total: $' + data.total_cost.toFixed(4);
                costDiv.appendChild(totalH4);

                var breakdownH5 = document.createElement('h5');
                breakdownH5.style.cssText = 'margin: 15px 0 10px 0;';
                breakdownH5.textContent = 'Service Breakdown:';
                costDiv.appendChild(breakdownH5);

                var services = Object.keys(data.service_breakdown);
                for (var i = 0; i < services.length; i++) {
                    var service = services[i];
                    var cost = data.service_breakdown[service];
                    var pct = data.cost_per_service_percentage[service];

                    var entryP = document.createElement('p');
                    entryP.style.cssText = 'padding: 8px; margin: 5px 0; background: white; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;';

                    var labelSpan = document.createElement('span');
                    labelSpan.textContent = service + ': $' + cost.toFixed(4);
                    entryP.appendChild(labelSpan);

                    var pctBadge = window.UI.createBadge(pct.toFixed(1) + '%', 'badge-advanced');
                    entryP.appendChild(pctBadge);

                    costDiv.appendChild(entryP);
                }

                panel.appendChild(costDiv);
            });
        } catch (error) {
            renderError('Admin access required');
        }
    }

    /**
     * Display per-user cost breakdown (admin only).
     *
     * Prompts for number of days (default 30). Calls
     * ApiClient.getAdminPerUserCost(tenantId, days) and renders:
     *   - Title with days count
     *   - Scrollable div with per-user entries showing cost,
     *     invocations, and tokens
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showAdminPerUserCost(tenantId) {
        var days = promptDays('Enter days for per-user cost report (default: 30):');
        if (days === null) {
            return;
        }

        try {
            var data = await window.ApiClient.getAdminPerUserCost(tenantId, days);

            window.UI.createInfoPanel('ADMIN: Per User Costs (' + days + ' days)', function (panel) {
                var scrollDiv = window.UI.createStyledDiv(
                    'max-height: 300px; overflow-y: auto;'
                );

                var users = Object.keys(data.users);
                for (var i = 0; i < users.length; i++) {
                    var userId = users[i];
                    var userData = data.users[userId];

                    var userDiv = window.UI.createStyledDiv(
                        'margin: 10px 0; padding: 10px; background: var(--nci-bg); border-radius: 3px;'
                    );

                    var nameStrong = document.createElement('strong');
                    nameStrong.textContent = userId + ':';
                    userDiv.appendChild(nameStrong);
                    userDiv.appendChild(document.createTextNode(' $' + userData.total_cost.toFixed(4)));
                    userDiv.appendChild(document.createElement('br'));

                    var small = document.createElement('small');
                    small.textContent = 'Invocations: ' + userData.usage_stats.invocations +
                        ', Tokens: ' + (userData.usage_stats.tokens.input + userData.usage_stats.tokens.output);
                    userDiv.appendChild(small);

                    scrollDiv.appendChild(userDiv);
                }

                panel.appendChild(scrollDiv);
            });
        } catch (error) {
            renderError('Admin access required');
        }
    }

    /**
     * Display service-wise cost breakdown (admin only).
     *
     * Prompts for number of days (default 30). Calls
     * ApiClient.getAdminServiceCost(tenantId, days) and renders:
     *   - Title with days count
     *   - Scrollable div with per-service entries showing cost,
     *     usage count, average cost, and peak day
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showAdminServiceCost(tenantId) {
        var days = promptDays('Enter days for service-wise cost report (default: 30):');
        if (days === null) {
            return;
        }

        try {
            var data = await window.ApiClient.getAdminServiceCost(tenantId, days);

            window.UI.createInfoPanel('ADMIN: Service-wise Costs (' + days + ' days)', function (panel) {
                var scrollDiv = window.UI.createStyledDiv(
                    'max-height: 300px; overflow-y: auto;'
                );

                var services = Object.keys(data.service_breakdown);
                for (var i = 0; i < services.length; i++) {
                    var service = services[i];
                    var serviceData = data.service_breakdown[service];

                    var serviceDiv = window.UI.createStyledDiv(
                        'margin: 10px 0; padding: 10px; background: #E3F2FD; border-radius: 3px;'
                    );

                    var nameStrong = document.createElement('strong');
                    nameStrong.textContent = service + ':';
                    serviceDiv.appendChild(nameStrong);
                    serviceDiv.appendChild(document.createTextNode(' $' + serviceData.total_cost.toFixed(4)));
                    serviceDiv.appendChild(document.createElement('br'));

                    var usageSmall = document.createElement('small');
                    usageSmall.textContent = 'Usage: ' + serviceData.usage_count +
                        ', Avg: $' + serviceData.average_cost_per_use.toFixed(6);
                    serviceDiv.appendChild(usageSmall);
                    serviceDiv.appendChild(document.createElement('br'));

                    var peakSmall = document.createElement('small');
                    peakSmall.textContent = 'Peak Day: ' + serviceData.peak_usage_day.date +
                        ' ($' + serviceData.peak_usage_day.cost.toFixed(4) + ')';
                    serviceDiv.appendChild(peakSmall);

                    scrollDiv.appendChild(serviceDiv);
                }

                panel.appendChild(scrollDiv);
            });
        } catch (error) {
            renderError('Admin access required');
        }
    }

    /**
     * Display the comprehensive admin cost report (admin only).
     *
     * Prompts for number of days (default 30). Calls
     * ApiClient.getAdminComprehensiveReport(tenantId, days) and renders:
     *   - Title with days count
     *   - Summary div with total cost, total users, highest cost
     *     service, most expensive user
     *   - Top users by cost list
     *
     * @param {string} tenantId - The tenant identifier.
     * @returns {Promise<void>}
     */
    async function showComprehensiveReport(tenantId) {
        var days = promptDays('Enter days for comprehensive admin report (default: 30):');
        if (days === null) {
            return;
        }

        try {
            var data = await window.ApiClient.getAdminComprehensiveReport(tenantId, days);

            window.UI.createInfoPanel('ADMIN: Comprehensive Cost Report (' + days + ' days)', function (panel) {
                var summaryDiv = window.UI.createStyledDiv(
                    'background: #FDECEA; padding: 15px; border-radius: 5px; border: 1px solid var(--nci-danger);'
                );

                var summaryH4 = document.createElement('h4');
                summaryH4.textContent = 'Summary';
                summaryDiv.appendChild(summaryH4);

                // Total Cost
                var totalCostP = document.createElement('p');
                var totalCostStrong = document.createElement('strong');
                totalCostStrong.textContent = 'Total Cost:';
                totalCostP.appendChild(totalCostStrong);
                totalCostP.appendChild(document.createTextNode(' $' + data.summary.total_tenant_cost.toFixed(4)));
                summaryDiv.appendChild(totalCostP);

                // Total Users
                var totalUsersP = document.createElement('p');
                var totalUsersStrong = document.createElement('strong');
                totalUsersStrong.textContent = 'Total Users:';
                totalUsersP.appendChild(totalUsersStrong);
                totalUsersP.appendChild(document.createTextNode(' ' + data.summary.total_users));
                summaryDiv.appendChild(totalUsersP);

                // Highest Cost Service
                var highCostP = document.createElement('p');
                var highCostStrong = document.createElement('strong');
                highCostStrong.textContent = 'Highest Cost Service:';
                highCostP.appendChild(highCostStrong);
                highCostP.appendChild(document.createTextNode(' ' + data.summary.highest_cost_service));
                summaryDiv.appendChild(highCostP);

                // Most Expensive User
                var expUserP = document.createElement('p');
                var expUserStrong = document.createElement('strong');
                expUserStrong.textContent = 'Most Expensive User:';
                expUserP.appendChild(expUserStrong);
                expUserP.appendChild(document.createTextNode(' ' + data.summary.most_expensive_user));
                summaryDiv.appendChild(expUserP);

                // Top Users by Cost
                var topH5 = document.createElement('h5');
                topH5.textContent = 'Top Users by Cost:';
                topH5.style.marginTop = '10px';
                summaryDiv.appendChild(topH5);

                var topUsers = Object.keys(data['4_top_users_by_cost']);
                for (var i = 0; i < topUsers.length; i++) {
                    var userId = topUsers[i];
                    var topUserData = data['4_top_users_by_cost'][userId];

                    var topUserP = document.createElement('p');
                    topUserP.textContent = userId + ': $' + topUserData.total_cost.toFixed(4);
                    summaryDiv.appendChild(topUserP);
                }

                panel.appendChild(summaryDiv);
            });
        } catch (error) {
            renderError('Admin access required');
        }
    }

    // -------------------------------------------------------------------------
    // Expose as window.AdminPanels namespace
    // -------------------------------------------------------------------------

    return {
        checkAdminAccess: checkAdminAccess,
        showUsage: showUsage,
        showSessions: showSessions,
        showSubscription: showSubscription,
        showAdminOverallCost: showAdminOverallCost,
        showAdminPerUserCost: showAdminPerUserCost,
        showAdminServiceCost: showAdminServiceCost,
        showComprehensiveReport: showComprehensiveReport
    };
})();
