"use strict"; 

var SchoologyApp = (function() {

  /**
   * Private Utils
   */
  function logger() {
    if(window.console) {
      console.log('Host: ', arguments, window.location.href);
    }
  }

  function getAppWindow(id) {
    var x = document.getElementById(id);
    return x.contentWindow;
  }


  var gradebookAppApi = function(chan) {

    return {

      /**
       * connect
       */
      connect: function(cb) {
        chan.bind('connect', cb);
      },

      /**
       * showDialog
       */
      showDialog: function(cb) {
        chan.bind('showDialog', cb);
      },

      /**
       * toolTipShow
       */
      toolTipShow: function(cb) {
        chan.bind('toolTipShow', cb);
      },

      /**
       * toolTipHide
       */
      toolTipHide: function(cb) {
        chan.bind('toolTipHide', cb);
      }

    };
  };

  var appApi = function(chan) {
    return {
      /**
       * connect
       */
      connect: function(cb) {
        chan.bind('connect', cb);
      },

      setHasUnsavedChanges: function(cb) {
        chan.bind('setHasUnsavedChanges', cb);
      }
    }
  }

  return {
    /**
     * Register gradebook app
     */
    register: function(appId, origin, context) {
      var chan = Channel.build({
        window: getAppWindow(appId),
        origin: origin,
        scope: context,
        reconnect: true,
      });
      logger('Listening in context=', context, ' for app=', appId, 'origin@', origin);
      return context === 'app' ? appApi(chan) : gradebookAppApi(chan);
    },
    /**
     * Public Utils
     */
    Utils: {
      logger: logger
    }
  };

})();
