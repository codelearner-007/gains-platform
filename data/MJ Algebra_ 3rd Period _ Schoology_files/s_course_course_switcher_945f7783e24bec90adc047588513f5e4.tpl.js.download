Drupal.theme.s_course_course_switcher = function(){
  var output = '';

  // course list
  output += '<ul ng-controller="s_course_switcher_courses" id="edit-course-switcher-select-nid-menu" role="menu" aria-label="' + Drupal.t('Switch course') + '" class="ui-selectmenu-menu ui-widget ui-widget-content ui-corner-all form-select" ng-class="{\'ui-selectmenu-open\':active}">';
    output += '<li role="none"><img ng-show="loading" class="ajax-loader" src="/sites/all/themes/schoology_theme/images/ajax-loader.gif" alt="' + Drupal.t('Loading') + '" /></li>';
    output += '<li class="ui-selectmenu-group" role="none" ng-repeat="course in courses" ng-show="course.display">';
      output += '<span class="ui-selectmenu-group-label">{{course.course_title}}</span>';
      output += '<ul role="group" aria-label="{{course.course_title}}">';
        output += '<li role="none" ng-repeat="section in course.sections" ng-show="section.display">';
         output += '<a href="{{section.link_to_current_page}}" role="menuitem" tabindex="-1" aria-label="{{course.course_title}} - {{section.section_title}}">';
         output += '{{section.section_title}}</a>';
        output += '</li>';
      output += '</ul>';
    output += '</li>';
  output += '</ul>';

  return output;
};
