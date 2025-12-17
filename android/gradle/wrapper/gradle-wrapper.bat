@echo off
set DIR=%~dp0
java -Xmx64m -Xms64m -classpath "%DIR%\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain %*
