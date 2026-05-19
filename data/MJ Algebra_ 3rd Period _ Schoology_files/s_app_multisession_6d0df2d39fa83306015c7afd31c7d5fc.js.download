(function(w) {
  var handled;
  w.addEventListener("message", receiveMessage, false);

  function showPopup()
  {
    var popup = new Popups.Popup();
    popup.extraClass = 'multisession_popup';
    var popup_params = {
      popup: popup,
      options: { hideActive: true },
      buttons: {
        'close': {
          title: Drupal.t('Close'),
          func: function( e ){
            var popup = Popups.activePopup();
            if( popup != null ){
              Popups.close( popup );
              var ifr_width = $('iframe#schoology-app-container').width();
              var ifr_height = $('iframe#schoology-app-container').height();
              $('iframe#schoology-app-container').replaceWith('<div id="schoology-app-div"></div>');
              $('#schoology-app-div').width(ifr_width).height(ifr_height);
            }
          }
        }
      }
    };

    var popupBody = '<div id="popup-alignment-form-wrapper">'+ Drupal.t('Your app session was closed by a newer session in another browser window or tab. Close the other window and then reload this one to resume this session') +'</div>';
    Popups.open( popup_params.popup , Drupal.t('Multiple App Sessions') , popupBody, popup_params.buttons , popup_params.width , popup_params.options );
    Popups.resizeAndCenter(popup);
  }

  function receiveMessage(event)
  {
    if (!handled && event.data == "SessionTracker:MultipleSessions") {
      var iframes = $('iframe#schoology-app-container');
      if (iframes.length > 0)
      {
        showPopup();
        handled = true;
      }
    }
  }
})(window);
