/**
 * API Client - Fetch wrappers with Bearer token authentication.
 *
 * Depends on:
 *   - window.Auth.getToken()  (JWT token provider)
 *   - CONFIG.apiUrl           (base URL for the backend API)
 */
window.ApiClient = (function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  /**
   * Build the full URL from a relative path.
   * @param {string} path - API path (e.g. "/api/sessions").
   * @returns {string} Fully-qualified URL.
   */
  function buildUrl(path) {
    var base = CONFIG.apiUrl.replace(/\/+$/, '');
    var cleanPath = path.replace(/^\/+/, '');
    return base + '/' + cleanPath;
  }

  /**
   * Return an Authorization header object using the current JWT.
   * @returns {Object} Headers dictionary with Authorization and Content-Type.
   */
  function authHeaders() {
    return {
      'Authorization': 'Bearer ' + window.Auth.getToken(),
      'Content-Type': 'application/json'
    };
  }

  // ---------------------------------------------------------------------------
  // Low-level request methods
  // ---------------------------------------------------------------------------

  /**
   * Perform an authenticated GET request.
   * @param {string} path - Relative API path.
   * @returns {Promise<Object>} Parsed JSON response.
   * @throws {Error} If the response status is not ok.
   */
  async function get(path) {
    var response = await fetch(buildUrl(path), {
      method: 'GET',
      headers: authHeaders()
    });

    if (!response.ok) {
      throw new Error(response.statusText);
    }

    return response.json();
  }

  /**
   * Perform an authenticated POST request with a JSON body.
   * @param {string} path - Relative API path.
   * @param {Object} [body] - Request payload (will be JSON-serialized).
   * @returns {Promise<Object>} Parsed JSON response.
   * @throws {Error} If the response status is not ok.
   */
  async function post(path, body) {
    var options = {
      method: 'POST',
      headers: authHeaders()
    };

    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }

    var response = await fetch(buildUrl(path), options);

    if (!response.ok) {
      throw new Error(response.statusText);
    }

    return response.json();
  }

  // ---------------------------------------------------------------------------
  // High-level domain methods
  // ---------------------------------------------------------------------------

  /**
   * Fetch usage statistics for a tenant.
   * @param {string} tenantId - The tenant identifier.
   * @returns {Promise<Object>} Usage data.
   */
  function getUsage(tenantId) {
    return get('/api/tenants/' + encodeURIComponent(tenantId) + '/usage');
  }

  /**
   * Fetch sessions for a tenant.
   * @param {string} tenantId - The tenant identifier.
   * @returns {Promise<Object>} Sessions data.
   */
  function getSessions(tenantId) {
    return get('/api/tenants/' + encodeURIComponent(tenantId) + '/sessions');
  }

  /**
   * Fetch subscription details for a tenant.
   * @param {string} tenantId - The tenant identifier.
   * @returns {Promise<Object>} Subscription data.
   */
  function getSubscription(tenantId) {
    return get('/api/tenants/' + encodeURIComponent(tenantId) + '/subscription');
  }

  /**
   * Create a new chat session.
   * @returns {Promise<Object>} Session creation response.
   */
  function createSession() {
    return post('/api/sessions');
  }

  /**
   * Send a chat message with tenant context.
   * @param {string} message - The user message text.
   * @param {Object} tenantContext - Tenant context object (tenant_id, user_id, session_id).
   * @returns {Promise<Object>} Chat response from the agent.
   */
  function sendMessage(message, tenantContext) {
    return post('/api/chat', {
      message: message,
      tenant_context: tenantContext
    });
  }

  /**
   * Fetch the list of tenants the current admin user manages.
   * @returns {Promise<Object>} Admin tenants data.
   */
  function getAdminTenants() {
    return get('/api/admin/my-tenants');
  }

  /**
   * Fetch overall cost report for a tenant (admin only).
   * @param {string} tenantId - The tenant identifier.
   * @param {number} days - Number of days to include in the report.
   * @returns {Promise<Object>} Overall cost data.
   */
  function getAdminOverallCost(tenantId, days) {
    return get(
      '/api/admin/tenants/' + encodeURIComponent(tenantId) +
      '/overall-cost?days=' + encodeURIComponent(days)
    );
  }

  /**
   * Fetch per-user cost breakdown for a tenant (admin only).
   * @param {string} tenantId - The tenant identifier.
   * @param {number} days - Number of days to include in the report.
   * @returns {Promise<Object>} Per-user cost data.
   */
  function getAdminPerUserCost(tenantId, days) {
    return get(
      '/api/admin/tenants/' + encodeURIComponent(tenantId) +
      '/per-user-cost?days=' + encodeURIComponent(days)
    );
  }

  /**
   * Fetch service-wise cost breakdown for a tenant (admin only).
   * @param {string} tenantId - The tenant identifier.
   * @param {number} days - Number of days to include in the report.
   * @returns {Promise<Object>} Service-wise cost data.
   */
  function getAdminServiceCost(tenantId, days) {
    return get(
      '/api/admin/tenants/' + encodeURIComponent(tenantId) +
      '/service-wise-cost?days=' + encodeURIComponent(days)
    );
  }

  /**
   * Fetch comprehensive admin cost report for a tenant (admin only).
   * @param {string} tenantId - The tenant identifier.
   * @param {number} days - Number of days to include in the report.
   * @returns {Promise<Object>} Comprehensive report data.
   */
  function getAdminComprehensiveReport(tenantId, days) {
    return get(
      '/api/admin/tenants/' + encodeURIComponent(tenantId) +
      '/comprehensive-report?days=' + encodeURIComponent(days)
    );
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    get: get,
    post: post,
    getUsage: getUsage,
    getSessions: getSessions,
    getSubscription: getSubscription,
    createSession: createSession,
    sendMessage: sendMessage,
    getAdminTenants: getAdminTenants,
    getAdminOverallCost: getAdminOverallCost,
    getAdminPerUserCost: getAdminPerUserCost,
    getAdminServiceCost: getAdminServiceCost,
    getAdminComprehensiveReport: getAdminComprehensiveReport
  };
})();
