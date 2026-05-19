(function () {
  /**
   * Prevent this from being declared multiple times
   */
  if (window._initGainsight) {
    return;
  }

  /**
   * Defines a method on `window` to initialize the Gainsight application
   * @see https://app-us2.aptrinsic.com/settings/products
   * @param {Object} user A subset of the user object
   * @param {Object} account Some school info
   * @param {String} apiKey The provided Gainsight tag key
   */
  window._initGainsight = function(user, account, apiKey) {
    // Prevent gainsight from being initialized multiple times
    if (window._gainsightInitialized) {
      return;
    }

    // Gainsight engine loading
    (function(n,t,a,e,co){var i="aptrinsic";n[i]=n[i]||function(){
      (n[i].q=n[i].q||[]).push(arguments)},n[i].p=e;n[i].c=co;
      var r=t.createElement("script");r.async=!0,r.src=a+"?a="+e;
      var c=t.getElementsByTagName("script")[0];c.parentNode.insertBefore(r,c)
    })(window,document,"https://web-sdk-us2.aptrinsic.com/api/aptrinsic.js",apiKey, { allowCrossDomain:true });

    // passing user and account objects:
    aptrinsic("identify", user, account);

    // Prevent initializing gainsight multiple times
    // This could occur from AJAX popups
    window._gainsightInitialized = true;
  }
})();
