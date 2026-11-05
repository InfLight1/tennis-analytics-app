Pod::Spec.new do |s|
  s.name           = 'AdvantageSend'
  s.version        = '1.0.0'
  s.summary        = 'Sends match videos in the background'
  s.description    = 'Splits a match video into pieces and sends them with a background transfer session.'
  s.author         = ''
  s.homepage       = 'https://github.com/InfLight1/tennis-analytics-app'
  s.platforms      = { :ios => '16.0' }
  s.source         = { git: '' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES' }
  s.source_files = '**/*.{h,m,mm,swift}'
end
