/*
 * LTI Submission Session Manager
 *
 * Usage:
 *   // Call this in main-footer.inc, which is included on all pages
 *   window.sAppLtiSubmissionSessionManager.init();
 *
 *   // Track LTI session URLs directly via JavaScript
 *   window.sAppLtiSubmissionSessionManager.trackUrl('https://lti-app.example.com/logout');
 *
 *   // Clear all LTI sessions (typically called on logout)
 *   window.sAppLtiSubmissionSessionManager.clearLtiSessions();
 */

/**
 * LTI Session Manager Module
 */
(function() {
  'use strict';

  function safeWarn() {
    if (typeof console !== 'undefined' && typeof console.warn === 'function') {
      console.warn.apply(console, arguments);
    }
  }

  /**
   * Storage Manager Class
   */
  function StorageManager() {
    const STORAGE_KEY = 's_app_lti_session_urls';

    let storageInterface = null;
    let isInitialized = false;

    function getBaseUrl(url) {
      if (typeof url !== 'string' || !url.trim()) {
        return null;
      }
      try {
        const urlObj = new URL(url);
        if (urlObj.protocol !== 'https:') {
          return null;
        }
        // Return base URL only
        return urlObj.protocol + '//' + urlObj.host;
      } catch (e) {
        return null;
      }
    }

    function normalizeUrls(urls) {
      return urls.map(getBaseUrl).filter(function (baseUrl) {
        return baseUrl !== null;
      });
    }

    function initializeStorage() {
      // Use sessionStorage exclusively - guaranteed available since app requires sessions
      try {
        // Test sessionStorage availability
        const testKey = '__sAppLtiTest__';
        window.sessionStorage.setItem(testKey, 'test');
        window.sessionStorage.removeItem(testKey);

        storageInterface = {
          get: () => window.sessionStorage.getItem(STORAGE_KEY),
          set: (data) => window.sessionStorage.setItem(STORAGE_KEY, data),
          clear: () => window.sessionStorage.removeItem(STORAGE_KEY)
        };
        isInitialized = true;
        return true;
      } catch (e) {
        safeWarn('LTI Session Manager: sessionStorage not available:', e.message);
        return false;
      }
    }

    // Public API for storage operations
    return {
      init: function () {
        return initializeStorage();
      },

      isInitialized: function () {
        return isInitialized;
      },

      getUrls: function () {
        if (!isInitialized || !storageInterface) {
          return [];
        }

        try {
          const jsonUrls = storageInterface.get();
          if (!jsonUrls) {
            return [];
          }
          return JSON.parse(jsonUrls);
        } catch (e) {
          safeWarn('LTI Session Manager: Error reading stored data:', e.message);
          return [];
        }
      },

      setUrls: function (urls) {
        if (!isInitialized || !storageInterface) {
          return false;
        }

        if (!Array.isArray(urls)) {
          safeWarn('LTI Session Manager: Invalid input to setUrls, expected array');
          return false;
        }

        try {
          const validUrls = normalizeUrls(urls);
          if (validUrls.length === 0) {
            return false;
          }
          const urlsJson = JSON.stringify(validUrls);
          storageInterface.set(urlsJson);
          return true;
        } catch (e) {
          safeWarn('LTI Session Manager: Failed to store URLs:', e.message);
          return false;
        }
      },

      clear: function () {
        if (storageInterface) {
          try {
            storageInterface.clear();
            return true;
          } catch (e) {
            safeWarn('LTI Session Manager: Failed to clear storage:', e.message);
            return false;
          }
        }
        return false;
      }
    };
  }

  /**
   * Handles iframe-based LTI session clearing
   */
  function ClearSessionRunner() {
    const SESSION_CLEAR_TIMEOUT_MS = 300; // Total time to wait for session clearing

    // The handler endpoint is in App Platform Apps lti_submission/src/routes/web.php
    const LTI_CLEAR_SESSION_ENDPOINT = '/lti/clear-session';

    /**
     * Creates a hidden container for LTI session clearing iframes
     */
    function createHiddenContainer() {
      const container = document.createElement('div');
      container.id = 'lti-session-clear-iframes';
      container.style.position = 'absolute';
      container.style.left = '-9999px';
      container.style.top = '-9999px';
      container.style.width = '1px';
      container.style.height = '1px';
      container.style.overflow = 'hidden';
      container.style.opacity = '0';
      container.style.pointerEvents = 'none';
      // Don't use display: none as it prevents iframe loading in some browsers
      // ensures the hidden container used for LTI session iframes does not interfere with accessibility tools
      container.setAttribute('aria-hidden', 'true');
      container.setAttribute('role', 'presentation');

      document.body.appendChild(container);
      return container;
    }

    function clearSingleSession(url, container) {
      return new Promise(function(resolve) {
        const clearSessionUrl = url.replace(/\/$/, '') + LTI_CLEAR_SESSION_ENDPOINT;

        const iframe = document.createElement('iframe');
        iframe.style.cssText = 'width:1px; height:1px; border:0; opacity:0; pointer-events:none;';
        iframe.referrerPolicy = 'no-referrer';

        try {
          container.appendChild(iframe);
          
          let completed = false;
          
          function cleanup() {
            if (!completed) {
              completed = true;
              if (iframe.parentNode) {
                try {
                  iframe.parentNode.removeChild(iframe);
                } catch (e) {
                  // Ignore
                }
              }
              resolve();
            }
          }
          
          // Safety timeout - fallback if request never completes
          const timeoutId = setTimeout(cleanup, SESSION_CLEAR_TIMEOUT_MS);
          
          iframe.onload = iframe.onerror = function() {
            // Completion on load or error, do early cleanup. This is not reliable though but if it works, great.
            clearTimeout(timeoutId);
            cleanup();
          };

          iframe.src = clearSessionUrl;
        } catch (e) {
          safeWarn('LTI Session Manager: Failed to create iframe for URL:', url);
          resolve();
        }
      });
    }

    return {
      clearSessions: function(urls) {
        if (!urls || !urls.length) {
          return Promise.resolve({processed: 0});
        }

        let container;
        try {
          container = document.getElementById('lti-session-clear-iframes') || createHiddenContainer();
        } catch (e) {
          safeWarn('LTI Session Manager: Failed to create iframe container:', e.message);
          return Promise.resolve({processed: 0});
        }

        const promises = urls.map(function(url) {
          return clearSingleSession(url, container);
        });
        
        return Promise.allSettled(promises).then(function(results) {
          return {
            processed: results.length
          };
        });
      }
    };
  }

  /**
   * Core LTI Submission Session Manager Class
   * Handles URL tracking and session cleanup for LTI applications
   */
  function LTISubmissionSessionManagerCore(storageManagerInstance) {
    let isInitialized = false;
    let storageManager = storageManagerInstance;
    let sessionRunner = new ClearSessionRunner();

    // Simple URL validation (basic check before passing to StorageManager)
    function isValidUrl(url) {
      if (typeof url !== 'string' || !url.trim()) {
        return false;
      }
      try {
        const urlObj = new URL(url);
        return urlObj.protocol === 'https:';
      } catch (e) {
        return false;
      }
    }

    // URL management functions using StorageManager
    function getStoredUrls() {
      if (!storageManager) {
        return [];
      }
      return storageManager.getUrls();
    }

    function setStoredUrls(urls) {
      if (!storageManager) {
        return false;
      }
      return storageManager.setUrls(urls);
    }

    function addUrl(url) {
      if (!isValidUrl(url)) {
        return;
      }

      // Get the base URL to check for duplicates
      let baseUrl;
      try {
        const urlObj = new URL(url);
        baseUrl = urlObj.protocol + '//' + urlObj.host;
      } catch (e) {
        return;
      }

      const trackedUrls = getStoredUrls();
      if (trackedUrls.indexOf(baseUrl) === -1) {
        trackedUrls.push(url); // Add the full URL, StorageManager will normalize it
        setStoredUrls(trackedUrls);
      }
    }

    function clearStorage() {
      if (storageManager) {
        return storageManager.clear();
      }
      return false;
    }

    // Public API - this object exposes the manager's functionality
    return {
      init: function () {
        if (isInitialized) {
          return true;
        }

        if (!storageManager) {
          safeWarn('LTI Session Manager: No storage manager provided');
          return false;
        }

        if (!storageManager.init()) {
          safeWarn('LTI Session Manager: Storage initialization failed');
          return false;
        }

        isInitialized = true;
        return true;
      },

      isInitialized: function () {
        return isInitialized;
      },

      ensureInitialized: function (operationName) {
        if (!isInitialized) {
          if (!this.init()) {
            console.error('LTI Session Manager: Cannot ' + operationName + ' - initialization failed');
            return false;
          }
        }
        return true;
      },

      trackUrl: function (ltiAppUrl) {
        if (!this.ensureInitialized('track URL')) {
          return this;
        }

        if (ltiAppUrl) {
          addUrl(ltiAppUrl);
        }
        return this;
      },

      hasLtiSessionsToClear: function () {
        if (!this.ensureInitialized('check sessions')) {
          return false;
        }
        return getStoredUrls().length > 0;
      },

      clearLtiSessions: function () {
        if (!this.ensureInitialized('clear sessions')) {
          return Promise.resolve({processed: 0});
        }

        return sessionRunner.clearSessions(getStoredUrls()).then(function (result) {
          clearStorage();
          return result;
        });
      }
    };
  }

  // Create the global LTI Session Manager instance and expose it directly through window.sAppLtiSubmissionSessionManager
  try {
    const storageManager = new StorageManager();
    window.sAppLtiSubmissionSessionManager = new LTISubmissionSessionManagerCore(storageManager);
  } catch (error) {
    safeWarn('LTI Session Manager failed to initialize:', error.message);

    // Provide fallback API
    window.sAppLtiSubmissionSessionManager = {
      init: function () {
        return this;
      },
      isInitialized: function () {
        return false;
      },
      trackUrl: function () {
        return this;
      },
      hasLtiSessionsToClear: function () {
        return false;
      },
      clearLtiSessions: function () {
        return Promise.resolve({processed: 0});
      }
    };
  }
})();
