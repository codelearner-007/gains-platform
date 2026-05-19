
Drupal.theme.prototype.popupButton = function(title, id) {
  return '<span><input type="button" value="'+ title +'" id="'+ id +'" /></span>';
};

Drupal.theme.prototype.popupLoading = function() {
  var loading = '<div id="popups-loading"><div>';
  loading += Drupal.t('Loading...');
  loading += '</div></div>';
  return loading;
};

Drupal.theme.prototype.popupDialog = function(popupId, title, body, buttons) { 
  var template = Drupal.theme('popupTemplate', popupId);
  if(buttons){
    body = '<div class="popups-body-inner-has-buttons">' + body + '</div>';
  }
  var popups = template.replace('%title', title).replace('%body', body);
  
  var themedButtons = '';
  if (buttons) {
    jQuery.each(buttons, function (id, button) {
      themedButtons += Drupal.theme('popupButton', button.title, id);
    });
    themedButtons = '<div class="popups-buttons-inner">' + themedButtons + '</div>';
  }  
  popups = popups.replace('%buttons', themedButtons);  
  return popups;
};

/**
 * Similar to drupal_attributes
 *
 * @param object attrs
 */
Drupal.attributes =
Drupal.theme.prototype.attributes = function(attrs){
  var ret = '';
  $.each(attrs, function(k, v){
    ret += ' ' + k + '="' + Drupal.checkPlain(v) +'"';
  });
  return $.trim(ret);
};

/**
 * Similar to Drupal's l()
 *
 * @param string text
 * @param string path
 * @param object opts
 */
Drupal.l =
Drupal.theme.prototype.l = function(text, path, opts){
  if(typeof opts == 'undefined'){
    var opts = {};
  }
  var defaults = {
    attributes: {},
    html: false
  };
  opts = $.extend(defaults, opts);
  
  return '<a href="' + path + '"' + Drupal.attributes(opts.attributes) + '>' + (opts.html ? text : Drupal.checkPlain(text))  + '</a>';
};

/**
 * Return a jquery object with the tipsy plugin bound.
 *
 * @param string content  the content to show in the tipsy
 * @param object opts
 *    string text        the text to go inside the element that triggers the tipsy
 *    string gravity     
 *    object attributes  standard Drupal.attributes
 */
Drupal.theme.infotip = function(content, opts){
  if(typeof opts == 'undefined'){
    var opts = {};
  }
  var defaults = {
    text: '',
    gravity: 's',
    attributes: {
      'class': ''
    }
  };
  opts = $.extend(defaults, opts);

  var el = '<span ' + Drupal.attributes(opts.attributes) + '>' + opts.text + '</span>';
  var infotipObj = $(el);
  infotipObj.tipsy({
    html: true,
    gravity: opts.gravity,
    title: function(){
      return content;
    }
  });

  return infotipObj;
};

/*
 * Return Markup for action links
 */
Drupal.theme.sActionLinks = function(links, opts){
  if(typeof opts == undefined){
    var opts = {};
  }
  
  if(typeof links != 'object' && links.length == 0){
    return '';
  }
  
  var defaults = {
    wrapperId : '',
    ulId : '',
    btnId : '',
    btnClass : '',
    ulClass : '',
    wrapperClass : '',
    size : 'regular',
    text : '',
    isAngular : true
  };
  opts = $.extend(defaults, opts);
  var output = '';
  output += '<div class="' + (opts.isAngular ? 's-action-link' : '') + ' action-links-wrapper action-links-wrapper-' + opts.size + ' ' + opts.wrapperClass + '">';
  output += '<div tabindex="0" role="button" class="action-links-unfold" id="' + opts.btnId + '">';
  output += '<span class="action-links-unfold-text"><span class="visually-hidden">' + Drupal.t('Click to toggle options.') + '</span></span>';
  output += '</div>';
  output += '<ul class="action-links">';
  $.each(links, function(k, v){
    output += v;
  });
  output += '</ul>';
  output += '</div>'; 
  return output;
}

Drupal.theme.sCommonAngularDeletePopup = function(){
  return {
    title : Drupal.t('Delete'),
    body : Drupal.t('Are you sure you want to delete this?'),
    confirm : {
      text : Drupal.t('Delete')
    },
    cancel : {
      text : Drupal.t('Cancel')
    }
  };
}

/**
 * Register an element for popups with the provided options.
 *
 * @param string/object el  selector or jquery object
 * @param object opts       popups options
 */
Drupal.popup = function(el, opts){
  var elObj = $(el)
  elObj.not('.popups-processed').addClass('popups-processed').click(function(e){
    e.preventDefault();
    return Popups.clickPopupElement(this, opts);
  });

  return elObj;
};

Drupal.behaviors.schoologyTheme = function(context){
  $('.popups-body textarea:not(.schoologyTheme-processed)').addClass('schoologyTheme-processed').each(function(){
    var ta = $(this);
    ta.focus(function(){
      ta.addClass('popups-textarea-focus');
	  popup = Popups.activePopup();
		if(popup != null)
				Popups.resizeAndCenter(popup);
    });
  });
};

Drupal.theme.sAjaxLoader = function(options){
  var defaultOpts = {
    asString : false,
    imgId : false
  };
  var opts = $.extend( {}, $.fn.sActionLinks.defaults, options);
  var ajaxLoader = $('<img />').attr('src','/sites/all/themes/schoology_theme/images/ajax-loader.gif').addClass('ajax-loader');
  
  if(opts.imgId){
    ajaxLoader.attr('id', opts.imgId);
  }
  
  if(opts.asString){
    return ajaxLoader[0].outerHTML;
  }
  return ajaxLoader;
}

Drupal.theme.sAjaxMessage = function(message, msgClass){
  var isError = ((msgClass || '').trim().split(/\s+/).indexOf('error') !== -1);
  var closeLabel = (typeof Drupal.sgyCloseLabel === 'function')
    ? Drupal.sgyCloseLabel()
    : Drupal.checkPlain(Drupal.t('Close message'));
  var liveRole = isError ? 'alert' : 'status';
  var liveAttrs = ' role="' + liveRole + '" aria-atomic="true" aria-relevant="additions text" tabindex="-1"';

 var msg = '<div class="messages ' + msgClass + '">\n\
          <div class="messages-container">\n\
            <table role="presentation"><tbody><tr>\n\
               <td><div class="messages-icon">&nbsp;</div></td>\n\
               <td><div class="message-text"' + liveAttrs + (isError ? ' aria-invalid="true"' : '') + '>' + message + '</div></td>\n\
            </tr></tbody></table>\n\
          </div>\n\
          <button type="button" tabindex="0" class="messages-close-btn"><span class="visually-hidden">' + closeLabel + '</span><span aria-hidden="true">x</span></button>\n\
        </div>';
  
  return msg;
}

Drupal.theme.s_course_no_members_overlay = function(course_nid, showNoMembers, showNoTags){
  var output = '';

  // default show no tags to false
  if(typeof showNoTags == 'undefined'){
    showNoTags = false;
  }

  // Default show no members to true
  if(typeof showNoMembers == 'undefined'){
    showNoMembers = true;
  }

  output += '<div class="s-js-no-members-overlay no-members-overlay hidden">';
  if(showNoMembers){
    output += '<div class="no-members-message">';
      output += '<span class="inline-icon medium students mono"></span>';
      output += Drupal.t('Currently there are no <a href="!members_link">members</a> in this course', {'!members_link': '/course/' + course_nid + '/members'});
    output += '</div>';
  }
  if(showNoTags && !showNoMembers){
    output += '<div class="no-tags-message">';
      output += '<span class="inline-icon medium tags mono"></span>';
      output += Drupal.t('There are no learning objectives aligned in this course');
    output += '</div>';
  }
  output += '</div>';

  return output;
};
