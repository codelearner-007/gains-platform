/**
 * Initialize sentry for the SGY core
 * 
 * @param {object} sentryConfig params needed to init sentry
 * @returns 
 */
function loadSentry() {
  const sentryConfig = getSentryConfig();
  if (sentryConfig) {
    return new Promise((resolve, reject) => {
      const isSentryLoaded = document.getElementById('sgy-core-sentry');
      if (!isSentryLoaded) {
        sentryScript = document.createElement("script");
        sentryScript.setAttribute("src", sentryConfig.scriptUrl);
        sentryScript.setAttribute("crossorigin", "anonymous");
        sentryScript.setAttribute("id", "sgy-core-sentry");
        document.body.appendChild(sentryScript);

        sentryScript.addEventListener("load", () => {
          Sentry.init({
            dsn: sentryConfig.dsnUrl,
            environment: sentryConfig.environment
          });
          resolve();
        });

        sentryScript.addEventListener("error", (error) => {
          console.error("Error while loading sentry", error);
          reject(error);
        });
      } else {
        resolve();
      }
    });
  } else {
    console.log('Sentry config not available. Skipping Sentry initialization.');
  }
}

/** getSentryConfig method responsible for fetching Sentry script url and dsn url */
function getSentryConfig() {
  if (window?.Drupal?.settings?.sentry) {
    return window.Drupal.settings.sentry;
  }
}