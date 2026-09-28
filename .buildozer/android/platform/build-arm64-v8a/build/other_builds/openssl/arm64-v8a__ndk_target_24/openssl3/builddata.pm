package OpenSSL::safe::installdata;

use strict;
use warnings;
use Exporter;
our @ISA = qw(Exporter);
our @EXPORT = qw($PREFIX
                  $BINDIR $BINDIR_REL
                  $LIBDIR $LIBDIR_REL
                  $INCLUDEDIR $INCLUDEDIR_REL
                  $APPLINKDIR $APPLINKDIR_REL
                  $ENGINESDIR $ENGINESDIR_REL
                  $MODULESDIR $MODULESDIR_REL
                  $PKGCONFIGDIR $PKGCONFIGDIR_REL
                  $CMAKECONFIGDIR $CMAKECONFIGDIR_REL
                  $VERSION @LDLIBS);

our $PREFIX             = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3';
our $BINDIR             = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3/apps';
our $BINDIR_REL         = 'apps';
our $LIBDIR             = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3';
our $LIBDIR_REL         = '.';
our $INCLUDEDIR         = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3/include';
our $INCLUDEDIR_REL     = 'include';
our $APPLINKDIR         = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3/ms';
our $APPLINKDIR_REL     = 'ms';
our $ENGINESDIR         = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3/engines';
our $ENGINESDIR_REL     = 'engines';
our $MODULESDIR         = '/workspaces/OTC-Analyzer/.buildozer/android/platform/build-arm64-v8a/build/other_builds/openssl/arm64-v8a__ndk_target_24/openssl3/providers';
our $MODULESDIR_REL     = 'providers';
our $PKGCONFIGDIR       = '';
our $PKGCONFIGDIR_REL   = '';
our $CMAKECONFIGDIR     = '';
our $CMAKECONFIGDIR_REL = '';
our $VERSION            = '3.3.1';
our @LDLIBS             =
    # Unix and Windows use space separation, VMS uses comma separation
    split(/ +| *, */, '-ldl -pthread -lm');

1;
