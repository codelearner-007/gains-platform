/**
 * Controller for course dropdown
 */
sAngular.addController('s_course_active_courses', ['$scope', 'Course', function($scope, Course){
  $scope.courses = null;
  $scope.permissions = null;
  $scope.loading = true;
  $scope.k6_infotip = Drupal.t('Schoology requires all instructors teaching students under the age of 13 to verify their identities. Students under the age of 13 cannot register for this course until you have been verified. Click here to verify your account.');
  $scope.load = function(callback){
    if($scope.courses === null){
      Course.getActiveCourses(function(courses, permissions){
        $scope.courses = courses;
        $scope.permissions = permissions;
        $scope.loading = false;
        var courseMap = {};
        $.each(courses.courses, function(i, course){
          courseMap[course.nid] = i;
        });
        $scope.courses.use_buildings_names = false;

        $.each(courses.sections, function(k, section){
          //setup sections array for course dropdown
          var course_index = courseMap[section.course_nid];
          var course = courses.courses[course_index];
          section.infotip = false;
          section.title = course.course_title + ': ' + section.section_title;

          if(!course.same_school || !course.same_building){
              $scope.courses.use_buildings_names = true;
          }
          section.building_title = course.building_title;
        });
        $.each(courses.courses, function(i, course){
          course.sections.sort(function(a, b){
            return a.section_title > b.section_title;
          });
        });
        
        if($scope.permissions.can_join_courses){
          $scope.join_course_link = Drupal.popup(Drupal.l(Drupal.t('Join'), '/enroll/course', {attributes: {'class': 'action-join', title: Drupal.t('Join Course')}}), {
              extraClass: 'popups-small',
              updateMethod: 'reload',
              hijackDestination: false,
              updateSource: 'final',
              doneTest: /course\/\d+?|home/,
              ajaxForm : true
            });
        }

        if($scope.permissions.can_create_courses){
          if($scope.permissions.school_has_grading_periods){
            $scope.create_course_link = Drupal.popup(Drupal.l(Drupal.t('Create'), '/course/create', {attributes: {'class': 'action-create', title: Drupal.t('Create Course')}}), {
              extraClass: 'popups-large popups-section',
              updateMethod: 'reload',
              hijackDestination: false,
              updateSource: 'final',
              doneTest: /course\/\d+/,
              ajaxForm : true
            });
          }
          else{
            $scope.create_course_link = Drupal.theme.infotip(Drupal.t('Grading periods must first be set up by your System Administrator'), {
              text: '<span class="action-create disabled">' + Drupal.t('Create') + '</span>',
              gravity: 'n',
              attributes: {
                'class': 'hide-qmark'
              }
            });
          }
        }
        if(typeof callback == 'function'){
          callback(courses, permissions);
          $('.no-active-courses-item').show();
        }
        
        $scope.loaded = true;
      });
    }
  };
  
}]);

/**
 * Retrieve courses to display on the course switcher
 */
sAngular.addController('s_course_switcher_courses', ['$scope', 'Course', function($scope, Course){
  if(!$scope.loaded){
    $scope.courses = null;
    $scope.permissions = null;
    $scope.loading = true;
  }
  $scope.load = function(callback){
    if($scope.courses === null){
      var params = {
        callback: function (data, permissions) {
          var currentPath = window.location.pathname.split('/'),
            currentPage = typeof currentPath[3] != 'undefined' ? currentPath[3] : '',
            courseMap = {};

            $scope.courses = data.courses;
            $scope.permissions = permissions;
            $scope.loading = false;

            $.each(data.courses, function (i, course) {
              courseMap[course.nid] = i;
              course.sections = [];

              // if it's the gradebook, only display the course if the user is an admin of one of the sections
              course.display = (currentPage != 'grades');
            });

            $.each(data.sections, function (i, section) {
              var course = data.courses[courseMap[section.course_nid]];

              // setup sections array for course switcher
              if (typeof course.sections != 'object') {
                course.sections = [];
              }
              currentPath[2] = section.nid;
              course.sections.push({
                link_to_current_page: currentPath.join('/'),
                section_title: section.section_title,
                is_admin: section.is_admin,
                // if it's the gradebook, only display the section if the user is an admin
                display: currentPage != 'grades' || section.is_admin
              });

              if (section.is_admin) {
                course.display = true;
              }
            });
            if (typeof callback == 'function') {
              callback(data, permissions);
            }
            $scope.loaded = true;
          },
          options: {
            no_upcoming: '1'
          }
        };
        Course.getActiveCourses(params);
      }
    };
}]);

sAngular.addController('s_course_course_export_user_search_box', ['$scope', function($scope){
  // this is just a placeholder for our js_template
}]);

sAngular.addDirective('sCourseCourseExportUserSearchBoxContainer', [function(){
  return {
    restrict: "C",
    controller: ['$scope', '$element', '$attrs', function($scope, $element, $attrs) {
      $scope.items = [];

      $scope.addItem = function(item) {
        $scope.items.push(item);
      };

      $scope.deleteItem = function(index) {
        $scope.items.splice(index, 1);
      };

      $scope.$on('sCourseCourseExportUserSearchBoxReset', function(e){
        $scope.items = [];
      });

    }],
    link: function(scope, element) {

      var searchBox = $('input', element);
      searchBox.val(Drupal.t('Search for users'));
      searchBox.addClass('search-box-init');
      searchBox.bind('click', function(e){
        if($(this).hasClass('search-box-init')) {
          $(this).val('');
          $(this).removeClass('search-box-init');
        }
      })
      .bind('focus', function(e){
        if($(this).hasClass('search-box-init')) {
          $(this).val('');
          $(this).removeClass('search-box-init');
        }
      })
      .bind('blur', function(e){
        if(!$(this).hasClass('search-box-init') && $(this).val() == '') {
          $(this).val(Drupal.t('Search for users'));
          $(this).addClass('search-box-init');
        }
      });

      var autocompleteWrapper = $('.autocomplete-wrapper', element);
      autocompleteWrapper.click(function(e){
        if(!$(e.target).hasClass('delete-selected')){
          searchBox.focus();
        }
      });

      searchBox.autocomplete('/iapi/course/search_users', {
        minChars: 3,
        scroll: true,
        dataType: 'json',
        width: (autocompleteWrapper.outerWidth() -2),
        anchorTo : autocompleteWrapper,

        parse: function(data){
          var data = data.body;

          var parsed = [];
          for(var i = 0; i < data.length; i++){
            var row = data[i];
            parsed[parsed.length] = {data: row, value: row.uid, result: ''};
          }

          if(parsed.length == 0) {
            var row = {uid: '', name: Drupal.t('No users found'), picture: ''};
            parsed[0] = {data: row, value: '', result: ''};
          }

          return parsed;
        },

        formatItem: function(row, i, max) {
          var rowHtml = '';
          rowHtml = '<div class="ac-row">';
          if(row.picture != '') {
            rowHtml += '<div class="ac-picture"><img src="' + row.picture + '" alt="' + Drupal.t('Profile picture for @node', { '@node': row.name }) + '" /></div>';
          }
          rowHtml += '<div class="ac-name">' + row.name + '</div>';
          rowHtml += '</div>';   
          return rowHtml;
        },
        
        formatResult: function(row) {
          return '';
        }
      });

      searchBox.result(function(event, data, formatted){
        $(this).val('');

        if($('.ac_results ul li .ac-row-default').length == 1 || data.uid == '') {
          return false;
        }

        var itemExists = false;
        $.each(scope.items, function(i, item){
          if(data.uid == item.uid) {
            itemExists = true;
          }
        });

        if(itemExists) {
          return false;
        }

        scope.$apply(function() { 
          scope.addItem(data);
          $('#edit-user-search-smart-box-field').val( $.toJSON(scope.items) );
        });

        return false;
      });

    }
  };
}]);