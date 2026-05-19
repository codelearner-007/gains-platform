Drupal.theme.prototype.popupTemplate = function(popupId) {
  var template = '';
  var titleId = popupId + '-title';
  template += '<div id="'+ popupId + '" class="popups-box" role="dialog" aria-labelledby="'+ titleId +'" aria-modal="true">';
  template += '  <div class="popups-title">';
  template += '    <div class="popups-close"><a href="javascript://" role="button"><span class="visually-hidden">' + Drupal.t('Close') + '</span></a></div>';
  template += '    <h2 class="title" id="'+ titleId +'">%title</h2>';
  template += '    <div class="clear-block"></div>';
  template += '  </div>';
  template += '  <div class="popups-body">%body</div>';
  template += '  <div class="popups-buttons">%buttons</div>';
  template += '  <div class="popups-footer"></div>';
  template += '</div>';
  return template;
};
